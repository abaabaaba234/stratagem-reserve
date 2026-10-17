-- Engine timestamps are microseconds. The adapter owns all native interaction.
local M={}
local TICKS=1000000
local function finite(n) return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge end
local function same(a,b)
    return a.manager==b.manager and a.entry==b.entry and a.owner==b.owner
        and a.slot==b.slot and a.type_id==b.type_id and a.clock==b.clock and a.definition==b.definition
end
function M.new(adapter,config,note)
    local self={slots={},blocked={},stopped=false,cleanup_pending=0,time=0,retry_at=0}
    note=note or function()end
    local function edit(s,field,old,value)
        local prior=s.edits[field]
        local e={field=field,old=prior and prior.old or old,last=value}
        s.edits[field]=e -- also retain ownership if a write reports a partial failure
        local okay=adapter.cas(s.id,field,old,value)
        e.failed=not okay
        assert(okay,field..' write failed')
    end
    local function restore(s)
        if adapter.clear_hud then pcall(adapter.clear_hud,s.id) end
        if not adapter.valid(s.id) then return true end -- retired allocation: never dereference it
        local okay=true
        for _,field in ipairs{'deadline','uses'} do
            local e=s.edits[field]
            if e then
                local current=adapter.read_field(s.id,field)
                if field=='uses' then
                    -- A finite mission allowance must also reflect a dispatch that
                    -- happened before shutdown or a failure prevented this tick.
                    local start=s.budget and adapter.read_field(s.id,'start')
                    if s.budget and current==e.last-1 and start and start>s.last_start then
                        s.budget=math.max(0,s.budget-1);e.old=s.budget;e.last=current;s.last_start=start
                    end
                    -- Native successful dispatch is allowed to decrement our last count.
                    if current==e.last or current==e.last-1 or current==e.old
                        or (e.failed and adapter.owned_prefix and adapter.owned_prefix(current,e.old,e.last)) then
                        if current~=e.old and not adapter.cas(s.id,field,current,e.old) then okay=false end
                    else okay=false end
                elseif current==nil then okay=false
                elseif current==e.last or current==e.old then
                    if current~=e.old and not adapter.cas(s.id,field,current,e.old) then okay=false end
                elseif e.failed and adapter.owned_prefix and adapter.owned_prefix(current,e.old,e.last) then
                    if not adapter.cas(s.id,field,current,e.old) then okay=false end
                else
                    -- Another writer owns the current deadline; do not overwrite it.
                    s.edits[field]=nil
                end
            end
        end
        return okay
    end
    local function retire(key,s,force)
        s.retiring=true
        if not force and self.time<(s.cleanup_at or 0) then return false end
        local okay,done=pcall(restore,s)
        if okay and done then self.slots[key]=nil;return true end
        s.cleanup_attempts=(s.cleanup_attempts or 0)+1
        s.cleanup_at=self.time+math.min(30,2^math.min(s.cleanup_attempts-1,5))
        return false
    end
    local function pending_count()
        local pending=0
        for _,s in pairs(self.slots)do if s.retiring then pending=pending+1 end end
        self.cleanup_pending=pending
        return pending
    end
    function self.release(reason,group,force)
        for key,s in pairs(self.slots) do
            if not group or s.group==group then
                retire(key,s,force)
            end
        end
        local pending=pending_count()
        if reason then note(reason..'; cleanup_pending='..pending) end
        return pending==0
    end
    function self.stop(reason)
        self.stopped=true;self.reason=tostring(reason)
        self.failures=(self.failures or 0)+1
        self.retry_at=self.time+math.min(30,2^math.min(self.failures-1,5))
        self.release('SUSPENDED: '..self.reason)
    end
    local function block(key,id,reason)
        local old=self.blocked[key]
        if not old or old.reason~=tostring(reason) then note(key..': paused; '..tostring(reason)) end
        local attempts=old and old.attempts or 0
        attempts=math.min(attempts+1,6)
        self.blocked[key]={id=id,reason=tostring(reason),attempts=attempts,
            retry_at=self.time+math.min(30,2^(attempts-1))}
        if self.slots[key] then retire(key,self.slots[key]) end
    end
    local function capacity(s)return math.min(config[s.group..'_max_charges'],s.budget or math.huge)end
    local function duration(s)
        return s.base_cd*config[s.group..'_cd_growth']^math.max(0,s.count-1)
    end
    local function rebase(s)
        local cycle=duration(s)
        assert(finite(cycle) and cycle>=1,'invalid reserve cycle')
        if config.inherit_ratio and s.cycle and s.cycle~=cycle then s.progress=s.progress*cycle/s.cycle end
        s.cycle=cycle
    end
    local function accrue(s,until_time)
        if until_time<s.last_now or capacity(s)==0 then return end
        local begin=math.max(s.last_now,s.blocked_until)
        if until_time<s.blocked_until then return end
        if s.count==0 then s.count=1;rebase(s);note(s.key..': full cooldown complete; count=1') end
        if s.count>=capacity(s) then s.progress=0;return end
        s.progress=s.progress+math.max(0,until_time-begin)/TICKS
        while s.progress+1e-7>=s.cycle and s.count<capacity(s) do
            s.progress=math.max(0,s.progress-s.cycle);s.count=s.count+1
            -- Surplus frame time belongs to the next stage as real elapsed time;
            -- it is not an inherited percentage of the stage that just completed.
            s.cycle=duration(s)
            note(s.key..': reserve gained; count='..s.count)
        end
        -- No hidden overflow credit once the capacity is reached.
        if s.count>=capacity(s) then s.progress=0 end
    end
    local function attach(x)
        for _,field in ipairs{'now','start','arrival','deadline'}do
            assert(finite(x[field]) and x[field]>=0 and x[field]<9007199254740991,'invalid '..field..' timestamp')
        end
        local limited=x.native_uses and x.native_uses~=0xffffffff
        assert((not limited and x.uses==0xffffffff) or (limited and x.uses>=0 and x.uses<=x.native_uses),
            'target current uses is modified; expected native allowance')
        assert(finite(x.base_cd) and x.base_cd>=1 and x.base_cd<=3600,'invalid effective cooldown')
        local block=math.max(x.deadline,x.arrival)
        local s={key=x.key,group=x.group,id=x,count=(block>x.now or x.uses==0) and 0 or 1,progress=0,
            budget=limited and x.uses or nil,base_cd=x.base_cd,cycle=x.base_cd,last_now=x.now,last_start=x.start,blocked_until=block,
            expected=x.uses,edits={}}
        self.slots[x.key]=s
        local wanted=s.budget==0 and 0 or math.max(1,s.count)
        edit(s,'uses',x.uses,wanted);s.expected=wanted
        note(x.key..': attached; count='..s.count..'; cycle='..s.cycle)
        return s
    end
    local function process(x,paused)
        for _,field in ipairs{'now','start','arrival','deadline'}do
            assert(finite(x[field]) and x[field]>=0 and x[field]<9007199254740991,'invalid '..field..' timestamp')
        end
        local s=self.slots[x.key]
        if s and not same(s.id,x) then
            assert(restore(s),'could not restore previous slot')
            self.slots[x.key]=nil;s=nil
        end
        if not s then
            if paused then return end
            s=attach(x);x.uses=s.expected
        end
        assert(x.now>=s.last_now,'mission clock moved backwards')
        assert(finite(x.base_cd) and x.base_cd>=1 and x.base_cd<=3600,'invalid effective cooldown')
        local dispatched=x.uses==s.expected-1
        if dispatched then
            assert(s.count>0 and x.start>s.last_start and x.arrival>=x.start
                and x.deadline>=x.arrival,'count changed without a successful native dispatch')
        else
            assert(x.uses==s.expected,'target uses changed by another writer')
        end
        if s.edits.deadline and x.deadline~=s.edits.deadline.last then
            assert(x.start>s.last_start,'short cooldown deadline changed by another writer')
            s.edits.deadline=nil -- a new native dispatch/failure superseded that timestamp
        end
        s.base_cd=x.base_cd
        s.count=math.min(s.count,capacity(s));rebase(s)
        if not paused then
            -- Credit only the ready portion before the native call started.
            accrue(s,x.start>s.last_start and math.min(x.now,x.start) or x.now)
        end
        if dispatched then
            s.count=s.count-1
            if s.budget then
                s.budget=s.budget-1;s.edits.uses.old=s.budget;s.edits.uses.last=x.uses;s.last_start=x.start
            end
            rebase(s)
            if s.count>0 then
                local deadline=x.arrival+math.floor(config.short_cooldown*TICKS+0.5)
                edit(s,'deadline',x.deadline,deadline);x.deadline=deadline
            end
            note(s.key..': native call consumed; count='..s.count..'; cooldown='..(s.count>0 and 'short' or 'full'))
        end
        s.blocked_until=math.max(x.deadline,x.arrival)
        if not paused and not dispatched and s.count==0 and capacity(s)>0 and x.now>=s.blocked_until then
            s.count=1
            rebase(s)
        end
        -- A native count of 0 selects EXHAUSTED before COOLDOWN in the HUD.
        -- Keep one inaccessible sentinel during full cooldown; present 0 in the HUD.
        local wanted=s.budget==0 and 0 or math.max(1,s.count)
        if x.uses~=wanted then edit(s,'uses',x.uses,wanted) end
        s.edits.uses.last=wanted -- accepted native decrements remain ours to restore
        s.expected=wanted;s.last_now=x.now;s.last_start=x.start;s.id=x
        s.ready=not paused and x.now>=s.blocked_until
        s.display={count=s.count,ready=s.ready,
            charging=s.ready and s.count<capacity(s),
            remaining=math.max(0,s.cycle-s.progress),cycle=s.cycle}
        if not paused then adapter.hud(x,s.display) end
    end
    function self.advance(dt)
        if finite(dt) and dt>=0 then self.time=self.time+dt end
    end
    function self.tick(dt)
        self.advance(dt)
        for key,s in pairs(self.slots)do if s.retiring then retire(key,s) end end
        pending_count()
        if self.stopped then
            self.release()
            if self.time<self.retry_at or self.cleanup_pending>0 then return end
            self.stopped=false
        end
        if not config.enabled then self.release();return end
        local context=adapter.snapshot(config,self.time)
        if not context or context.inactive then self.release();self.blocked={};self.inactive=true;return end
        self.inactive=false;self.failures=0
        local seen={}
        for key,why in pairs(context.blocked or {})do
            seen[key]=true;block(key,nil,why.reason)
        end
        for _,x in ipairs(context.targets) do
            if config[x.group..'_enabled'] then
                seen[x.key]=true
                local b=self.blocked[x.key]
                if b and b.id and not same(b.id,x) then self.blocked[x.key]=nil;b=nil end
                local s=self.slots[x.key]
                if not (s and s.retiring) and (not b or self.time>=b.retry_at) then
                    local okay,why=pcall(process,x,context.paused)
                    if okay then
                        if b then note(x.key..': resumed')end
                        self.blocked[x.key]=nil
                    else block(x.key,x,why) end
                end
            end
        end
        for key,s in pairs(self.slots) do
            if not seen[key] then retire(key,s) end
        end
        for key in pairs(self.blocked)do if not seen[key]then self.blocked[key]=nil end end
        pending_count()
    end
    self.same= same
    return self
end
return M
