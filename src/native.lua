-- Layout compatibility is checked independently of game version metadata.
-- No executable patches, static cooldown edits or remote slots.
local ffi=require('ffi')
local M={}
local kernel={}
for _,d in ipairs{
    {'GetCurrentProcess','void *','(void)'},
    {'GetModuleHandleA','void *','(const char *)'},
    {'ReadProcessMemory','int','(void *, const void *, void *, size_t, size_t *)'},
    {'WriteProcessMemory','int','(void *, void *, const void *, size_t, size_t *)'},
    {'VirtualQuery','size_t','(const void *, void *, size_t)'},
    {'MoveFileExA','int','(const char *, const char *, uint32_t)'},
} do
    local alias='stratreserve_'..d[1]
    ffi.cdef(d[2]..' '..alias..d[3]..' __asm__("'..d[1]..'");')
    kernel[d[1]]=ffi.load('kernel32')[alias]
end
local function unhex(h) return (h:gsub('..',function(v)return string.char(tonumber(v,16))end)) end
local function u32(s,o)
    if not s then return nil end
    local a,b,c,d=s:byte(o+1,o+4);return d and a+b*256+c*65536+d*16777216
end
local function u64(s,o) return s and u32(s,o)+u32(s,o+4)*4294967296 end
local function packed(n,ctype) return ffi.string(ffi.new(ctype..'[1]',n),ffi.sizeof(ctype)) end
local ANCHORS={
    -- Local player history lookup and current-use getter.
    {0x1366dc0,'448b8900d2020033c04c8bd14585c974164c8bc1493910'},
    {0x66d3d0,'4883ec28418bc04c8d1522e21503488d0c404803c98b84ca8c010000'},
    -- Success branch: arrival deadline, finite-use decrement; cooldown endpoint.
    {0x135c6f5,'418d40ff48898cfde001000083f8fd773441ffc8448984fdc4010000'},
    {0x135c41b,'4889841fd8010000'},
    -- Effective cooldown includes native upgrades and mission modifiers.
    {0x8796a0,'488bc44883ec780f2970d8440f2940b8'},
    -- HUD ready/cooling distinction; plain UTF-8 text and shown setter.
    {0x1836bea,'f3410f108720370000410f2fc3760ac744245404000000'},
    {0x143dd60,'48895c24084889742410574883ec204885d2'},
    {0x14508e0,'4883ec28448b014c8bd1418bc0458bc883e0ef4183c91084d2440f44c8'},
    -- Per-row type/index and status text object.
    {0x1836759,'8945d0418b94ca880100004189974c370000'},
    {0x1838092,'498d8f28200000e8d25dc0ff'},
    -- Native count renderer: preserve the localized number template, measure text,
    -- and resize its badge/background instead of replacing its string with plain text.
    {0x183ae60,'48895c24104889742418574883ec30488db920090000'},
    {0x183aef1,'448b86bc140000488d8ee00c0000ba357b2aabe8c71bc0ff488d8ee00c0000e88b32c1ff'},
}
function M.new(targets,note)
    note=note or function()end
    local api={writes=0,hud_updates=0}
    local process=kernel.GetCurrentProcess()
    local by_type={}
    for _,t in ipairs(targets)do
        assert(not by_type[t.type_id] and (t.group=='green' or t.group=='blue' or t.group=='red'),'invalid target registry')
        by_type[t.type_id]=t
    end
    local buffer=ffi.new('uint8_t[512]');local got=ffi.new('size_t[1]')
    local mbi=ffi.new('uint8_t[48]')
    local function read(p,n)
        if not p or p<0x10000 or p+n>0x7fffffff0000 or n<1 or n>512 then return nil end
        got[0]=0
        if kernel.ReadProcessMemory(process,ffi.cast('const void *',p),buffer,n,got)==0 or tonumber(got[0])~=n then return nil end
        return ffi.string(buffer,n)
    end
    local function ptr(p)return u64(read(p,8),0)end
    local function uint(p)return u32(read(p,4),0)end
    local function byte(p)local b=read(p,1);return b and b:byte()end
    local function write(p,bytes)
        -- Only committed private read/write memory. Never change page protection.
        if kernel.VirtualQuery(ffi.cast('const void *',p),mbi,48)~=48 then return false end
        local region=ffi.string(mbi,48)
        if u32(region,32)~=0x1000 or u32(region,36)~=4 or u32(region,40)~=0x20000
            or p+#bytes>u64(region,0)+u64(region,24) then return false end
        got[0]=0
        local okay=kernel.WriteProcessMemory(process,ffi.cast('void *',p),bytes,#bytes,got)~=0 and tonumber(got[0])==#bytes
        if okay and read(p,#bytes)==bytes then api.writes=api.writes+1;return true end
        return false
    end
    local base,checked=false,false
    local effective_cd,text_set,count_draw
    local overlays={}
    local function build()
        if checked then return base end
        base=tonumber(ffi.cast('uintptr_t',kernel.GetModuleHandleA('game.dll')))
        if not base or base==0 then return nil end
        local dos=read(base,64);assert(dos and dos:sub(1,2)=='MZ','invalid game.dll header')
        local offset=u32(dos,60);assert(offset>=64 and offset<=4096-96,'invalid PE offset')
        local pe=read(base+offset,96)
        assert(pe and pe:sub(1,4)=='PE\0\0' and pe:sub(5,6)=='\100\134' and pe:sub(25,26)=='\11\2'
            and u32(pe,80)>0x37cc000,'unsupported game.dll layout')
        for _,a in ipairs(ANCHORS) do
            local expected=unhex(a[2]);assert(read(base+a[1],#expected)==expected,'code identity differs at '..string.format('%x',a[1]))
        end
        effective_cd=ffi.cast('float (*)(uintptr_t, uint64_t, uint32_t, uint8_t, uint8_t)',base+0x8796a0)
        text_set=ffi.cast('uint8_t (*)(uintptr_t, const char *)',base+0x143dd60)
        count_draw=ffi.cast('void (*)(uintptr_t)',base+0x183ae60)
        checked=true;note('game.dll layout and native code anchors verified; PE timestamp='..u32(pe,8))
        return base
    end
    local function definition(t)
        local address=ptr(base+0x37cb600+t.type_id*8)
        if not address or address==0 then return nil end
        local raw=read(address,400);assert(raw,'target StratagemInfo unavailable')
        local nameptr=ptr(base+0x21d4aa0+t.type_id*8)
        local name=nameptr and read(nameptr,64)
        assert(u32(raw,0)==t.type_id and name and name:match('^([^%z]+)')==t.internal_name
            and u32(raw,0x3c)==t.category and u32(raw,0x50)==(t.native_uses or 0xffffffff)
            and u32(raw,0x94)==0 and u32(raw,0xa0)==#t.payloads,'target definition differs')
        local p=u64(raw,0x98);local payload=read(p,#t.payloads*8)
        local expected='';for _,h in ipairs(t.payloads)do expected=expected..unhex(h)end
        assert(payload==expected,'target payload identity differs')
        -- Cooldown is live tuning, not identity. Finite-use semantics remain guarded.
        local f=ffi.new('float[1]');ffi.copy(f,raw:sub(105,108),4)
        local cooldown=tonumber(f[0]);local allowance=u32(raw,0x50)
        assert(cooldown==cooldown and cooldown>=1 and cooldown<=3600,'invalid base cooldown')
        assert(allowance==0xffffffff or allowance<=1000,'invalid native allowance')
        return address,allowance
    end
    function api.valid(id)
        if not base or ptr(base+0x347ce50)~=id.manager or ptr(base+0x3326348)~=id.clock then return false end
        local total=uint(id.manager+0x2d200)
        if not total or total>32 or id.entry<id.manager or id.entry>=id.manager+total*0x1690
            or (id.entry-id.manager)%0x1690~=0 then return false end
        local rows=uint(id.entry+0x7c0)
        return rows and rows<=32 and read(id.entry,8)==id.owner and rows>id.slot
            and uint(id.address)==id.type_id
            and ptr(base+0x37cb600+id.type_id*8)==id.definition
    end
    local fields={uses={4,'uint32_t',4},deadline={0x18,'uint64_t',8},start={0x10,'uint64_t',8}}
    function api.read_field(id,field)
        if not api.valid(id) then return nil end
        local f=assert(fields[field]);local b=read(id.address+f[1],f[3])
        return b and (f[3]==4 and u32(b,0) or u64(b,0))
    end
    function api.cas(id,field,expected,value)
        assert(field=='uses' or field=='deadline','read-only native field')
        if not api.valid(id) then return false end
        local f=assert(fields[field]);local address=id.address+f[1]
        if read(address,f[3])~=packed(expected,f[2]) then return false end
        return write(address,packed(value,f[2]))
    end
    function api.owned_prefix(current,old,wanted)
        if not current then return false end
        local c,a,b=packed(current,'uint64_t'),packed(old,'uint64_t'),packed(wanted,'uint64_t')
        for n=0,8 do if c==b:sub(1,n)..a:sub(n+1)then return true end end
        return false
    end
    local rejected={}
    function api.snapshot(config,time)
        time=time or 0
        if not build() then return {inactive=true} end
        local scene=ptr(base+0x3326340)
        if not scene or uint(scene+0xac21c)~=4 then return {inactive=true} end
        local player=ptr(base+0x3326468);local manager=ptr(base+0x347ce50)
        local clock=ptr(base+0x3326348);local hud=ptr(base+0x346d538)
        if not player or not manager or not clock or not hud then return {inactive=true} end
        local localcount=uint(player+0x88)
        if localcount~=1 then return {inactive=true} end
        local owner=read(player+0x2c8,8)
        if not owner or owner==string.rep('\0',8) or owner==string.rep('\255',8)then return {inactive=true}end
        local count=uint(manager+0x2d200);assert(count and count<=32,'invalid player history count')
        local entry
        for i=0,count-1 do
            local p=manager+i*0x1690
            if read(p,8)==owner then assert(not entry,'ambiguous local owner');entry=p end
        end
        if not entry then return {inactive=true} end
        local rows=uint(entry+0x7c0);assert(rows and rows<=32,'invalid stratagem slot count')
        local now=ptr(clock+0x18);assert(now and now<9007199254740991,'invalid mission clock')
        local mission=hud+0x24e340
        local paused=byte(mission+0x59)~=0 or byte(mission+0x21f5b0)~=1
        local result={paused=paused,targets={},blocked={}}
        local upgrades=ptr(base+0x33264f8)
        if not upgrades or upgrades<0x10000 then return {inactive=true} end
        local found,slot_lists={},{}
        for slot=0,rows-1 do
            local type_id=uint(entry+0x1c0+slot*48)
            if by_type[type_id] then
                found[type_id]=(found[type_id] or 0)+1
                slot_lists[type_id]=(slot_lists[type_id] and slot_lists[type_id]..',' or '')..slot
            end
        end
        local present={}
        -- Check only equipped, enabled targets. An unrelated or disabled definition
        -- must not stop the active group, nor impose reads for the entire registry.
        for slot=0,rows-1 do
            local address=entry+0x1c0+slot*48
            local t=by_type[uint(address)]
            if t and config[t.group..'_enabled'] then
                present[t.key]=true
                local previous=rejected[t.key]
                local okay,def,allowance
                if found[t.type_id]>1 then
                    okay=false;def='duplicate target slots; type='..t.type_id..'; slots='..slot_lists[t.type_id]
                elseif previous and time<previous.retry_at then
                    okay=false;def=previous.reason
                else
                    okay,def,allowance=pcall(definition,t)
                end
                if not okay then
                    if not previous or time>=previous.retry_at or previous.reason~=tostring(def) then
                        rejected[t.key]={reason=tostring(def),retry_at=time+5}
                    end
                    result.blocked[t.key]={reason=tostring(def),type_id=t.type_id,slot=slot}
                    def=nil
                else rejected[t.key]=nil end
                if def then
                    local sampled,target=pcall(function()
                    local b=assert(read(address,48),'target slot unavailable')
                    local cycle=tonumber(effective_cd(upgrades,ffi.cast('uint64_t *',owner)[0],t.type_id,0,0))
                    return {key=t.key,group=t.group,type_id=t.type_id,native_uses=allowance,manager=manager,
                        entry=entry,owner=owner,slot=slot,address=address,definition=def,
                        clock=clock,now=now,uses=u32(b,4),start=u64(b,0x10),
                        deadline=u64(b,0x18),arrival=u64(b,0x20),base_cd=cycle,hud=hud}
                    end)
                    if sampled then result.targets[#result.targets+1]=target
                    else
                        rejected[t.key]={reason=tostring(target),retry_at=time+5}
                        result.blocked[t.key]={reason=tostring(target),type_id=t.type_id,slot=slot}
                    end
                end
            end
        end
        for key in pairs(rejected)do if not present[key]then rejected[key]=nil end end
        return result
    end
    local function widget_text(widget)
        local external=ptr(widget+0x110)
        local b=external and external~=0 and read(external,256) or read(widget+0x11c,256)
        return b and b:find('\0',1,true) and b:match('^([^%z]*)')
    end
    function api.clear_hud(id)
        local e=overlays[id.key]
        if not e then return end
        overlays[id.key]=nil
        if api.valid(id) and ptr(base+0x346d538)==e.hud
            and uint(e.row+0x3748)==id.slot and uint(e.row+0x374c)==id.type_id
            and widget_text(e.widget)==e.last then text_set(e.widget,e.original) end
    end
    function api.hud(id,display)
        if not api.valid(id) or ptr(base+0x346d538)~=id.hud then return end
        if not display.charging then api.clear_hud(id) end
        local list=id.hud+0x24e340+0x146dc0+0x1040
        -- Native list can arrange slots differently. Match its actual type AND slot.
        for i=0,15 do
            local row=list+0x110+i*0x3760
            local tail=read(row+0x36f0,112)
            if tail and u32(tail,0x58)==id.slot and u32(tail,0x5c)==id.type_id
                and tail:byte(1)==1 then
                local card=row+0x7c0
                local cardinfo=read(card+0x14b8,24)
                if cardinfo and u32(cardinfo,0)==id.slot and u32(cardinfo,16)==id.type_id then
                    -- During full cooldown the gameplay slot contains a blocked
                    -- sentinel, but the badge must show the real reserve count 0.
                    -- Override only this UI cache for the native draw, then restore
                    -- it so the next normal HUD tick can still detect changes.
                    local cache=card+0x14bc
                    local original=u32(cardinfo,4)
                    local changed=original~=display.count
                    if not changed or (api.valid(id) and uint(cache)==original
                        and write(cache,packed(display.count,'uint32_t'))) then
                        local okay,why=pcall(count_draw,card)
                        local restored=not changed
                        if changed and api.valid(id) and uint(cache)==display.count then
                            restored=write(cache,packed(original,'uint32_t'))
                        end
                        assert(restored,'HUD count cache restore failed')
                        assert(okay,'native HUD count renderer failed: '..tostring(why))
                        api.hud_updates=api.hud_updates+1
                    end
                end
                if display.charging and u32(tail,0x68)==1 then
                    local widget=row+0x2028
                    local e=overlays[id.key]
                    if e and (e.widget~=widget or e.hud~=id.hud)then api.clear_hud(id);e=nil end
                    if not e then
                        local original=widget_text(widget)
                        if original then
                            e={widget=widget,row=row,hud=id.hud,original=original};overlays[id.key]=e
                        end
                    end
                    local secs=math.ceil(display.remaining)
                    if e then
                        e.last=string.format('储备补充 %02d:%02d',math.floor(secs/60),secs%60)
                        text_set(widget,e.last)
                    end
                    -- Preserve the native ready icon, colours, input and widget layout.
                end
            end
        end
    end
    function api.save(path,text)
        local temp=path..'.tmp';local f,why=io.open(temp,'wb');if not f then return false,why end
        local okay=f:write(text);local flushed=f:flush();local closed=f:close()
        if not okay or not flushed or not closed then os.remove(temp);return false,'config I/O failed'end
        if kernel.MoveFileExA(temp,path,9)==0 then os.remove(temp);return false,'config replace failed'end
        return true
    end
    api.anchors=ANCHORS
    return api
end
return M
