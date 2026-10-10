-- Engine timestamps are microseconds. The adapter owns all native interaction.
local M={}
local TICKS=1000000
local function finite(n) return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge end
local function same(a,b)
    return a.manager==b.manager and a.entry==b.entry and a.owner==b.owner
        and a.slot==b.slot and a.type_id==b.type_id and a.clock==b.clock
end
function M.new(adapter,config,note)
    local self={slots={},stopped=false,cleanup_pending=0}
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
                    -- Native successful dispatch is allowed to decrement our last count.
                    if current==e.last or current==e.last-1 or current==e.old
                        or (e.failed and adapter.owned_prefix and adapter.owned_prefix(current,e.old,e.last)) then
                        if current~=e.old and not adapter.cas(s.id,field,current,e.old) then okay=false end
                    else okay=false end
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
    function self.release(reason,group)
        local pending=0
        for key,s in pairs(self.slots) do
            if not group or s.group==group then
                if restore(s) then self.slots[key]=nil else pending=pending+1 end
            end
        end
        self.cleanup_pending=pending
        if reason then note(reason..'; cleanup_pending='..pending) end
        return pending==0
    end
    function self.stop(reason)
        self.stopped=true;self.reason=tostring(reason);self.release('STOPPED: '..self.reason)
    end
    local function accrue(s,until_time)
        if until_time<=s.last_now then return end
        local begin=math.max(s.last_now,s.blocked_until)
        if until_time<s.blocked_until then return end
        if s.count==0 then s.count=1;note(s.key..': full cooldown complete; count=1') end
        if s.count>=config.max_charges then return end
        s.progress=s.progress+math.max(0,until_time-begin)/TICKS
        while s.progress+1e-7>=s.cycle and s.count<config.max_charges do
            s.progress=math.max(0,s.progress-s.cycle);s.count=s.count+1
            note(s.key..': reserve gained; count='..s.count)
        end
        -- No hidden overflow credit once the capacity is reached.
        if s.count>=config.max_charges then s.progress=0 end
    end
    local function attach(x)
        for _,field in ipairs{'now','start','arrival','deadline'}do
            assert(finite(x[field]) and x[field]>=0 and x[field]<9007199254740991,'invalid '..field..' timestamp')
        end
        assert(x.uses==0xffffffff,'target current uses is modified; expected native unlimited')
        assert(finite(x.base_cd) and x.base_cd>=1 and x.base_cd<=3600,'invalid effective cooldown')
        local block=math.max(x.deadline,x.arrival)
        local s={key=x.key,group=x.group,id=x,count=block>x.now and 0 or 1,progress=0,
            cycle=x.base_cd,last_now=x.now,last_start=x.start,blocked_until=block,
            expected=x.uses,edits={}}
        self.slots[x.key]=s
        edit(s,'uses',x.uses,math.max(1,s.count));s.expected=math.max(1,s.count)
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
        s.cycle=x.base_cd
        s.count=math.min(s.count,config.max_charges)
        if not paused then
            -- Credit only the ready portion before the native call started.
            accrue(s,x.start>s.last_start and math.min(x.now,x.start) or x.now)
        end
        if dispatched then
            s.count=s.count-1
            if s.count>0 then
                local deadline=x.arrival+math.floor(config.short_cooldown*TICKS+0.5)
                edit(s,'deadline',x.deadline,deadline);x.deadline=deadline
            end
            note(s.key..': native call consumed; count='..s.count..'; cooldown='..(s.count>0 and 'short' or 'full'))
        end
        s.blocked_until=math.max(x.deadline,x.arrival)
        if not paused and not dispatched and s.count==0 and x.now>=s.blocked_until then
            s.count=1
        end
        -- A native count of 0 selects EXHAUSTED before COOLDOWN in the HUD.
        -- Keep one inaccessible sentinel during full cooldown; present 0 in the HUD.
        local wanted=math.max(1,s.count)
        if x.uses~=wanted then edit(s,'uses',x.uses,wanted) end
        s.edits.uses.last=wanted -- accepted native decrements remain ours to restore
        s.expected=wanted;s.last_now=x.now;s.last_start=x.start;s.id=x
        s.ready=not paused and x.now>=s.blocked_until
        s.display={count=s.count,ready=s.ready,
            charging=s.ready and s.count<config.max_charges,
            remaining=math.max(0,s.cycle-s.progress),cycle=s.cycle}
        if not paused then adapter.hud(x,s.display) end
    end
    function self.tick()
        if self.stopped then self.release();return end
        if not config.enabled then self.release();return end
        local context=adapter.snapshot(config)
        if not context or context.inactive then self.release();return end
        local seen={}
        for _,x in ipairs(context.targets) do
            if (x.group=='green' and config.green_enabled) or (x.group=='blue' and config.blue_enabled) then
                seen[x.key]=true;process(x,context.paused)
            end
        end
        for key,s in pairs(self.slots) do
            if not seen[key] then assert(restore(s),'could not restore removed slot');self.slots[key]=nil end
        end
    end
    self.same= same
    return self
end
return M
