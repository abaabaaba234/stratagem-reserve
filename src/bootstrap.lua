local existing=rawget(_G,'StratagemReserve')
if existing then return existing end
local S={version='0.3.0',phase='initializing',ingame_tested=false,multiplayer_tested=false}
rawset(_G,'StratagemReserve',S)
local loader=rawget(_G,'CowboyBingusModLoader')
if type(loader)~='table' or loader.api~=1 or type(loader.open_log)~='function' or type(loader.jit)~='table' then
    S.phase='stopped';S.reason='Bingus Shared Loader v18 / API 1 required'
    pcall(print,'[StratagemReserve] '..S.reason);return S
end
local logfile
pcall(function() logfile=loader.open_log('StratagemReserve.log') end)
local function note(line)
    S.status=tostring(line);pcall(print,'[StratagemReserve] '..S.status)
    if logfile then pcall(function()logfile:write(os.date('%H:%M:%S ')..S.status..'\n');logfile:flush()end)end
end
local native=Native.new(Targets,note);S.native=native
local groups={'red','green','blue'}
local function defaults()
    local c={enabled=true,inherit_ratio=false,short_cooldown=5}
    for _,group in ipairs(groups)do c[group..'_enabled']=true;c[group..'_max_charges']=3;c[group..'_cd_growth']=1 end
    return c
end
local config=defaults();S.config=config
local folder=type(loader.log_directory)=='string' and loader.log_directory
    or (os.getenv('LOCALAPPDATA') or '')..'\\CowboyBingus\\Helldivers2\\Logs'
local path=folder..'\\StratagemReserve.cfg';S.config_path=path
local function config_text(c)
    local text='# Stratagem Reserve. Group caps are total callable uses.\nenabled='..(c.enabled and '1' or '0')
        ..'\ninherit_ratio='..(c.inherit_ratio and '1' or '0')..'\nshort_cooldown='..c.short_cooldown..'\n'
    for _,group in ipairs(groups)do
        text=text..group..'_enabled='..(c[group..'_enabled'] and '1' or '0')..'\n'
            ..group..'_max_charges='..c[group..'_max_charges']..'\n'
            ..group..'_cd_growth='..c[group..'_cd_growth']..'\n'
    end
    return text
end
local function number(n,low,high,step)
    return type(n)=='number' and n==n and n>=low and n<=high and math.abs(n/step-math.floor(n/step+0.5))<1e-7
end
local function validate(c)
    if type(c.enabled)~='boolean' or type(c.inherit_ratio)~='boolean' or not number(c.short_cooldown,1,60,0.5)then return false end
    for _,group in ipairs(groups)do
        if type(c[group..'_enabled'])~='boolean' or not number(c[group..'_max_charges'],1,10,1)
            or not number(c[group..'_cd_growth'],1,3,0.1)then return false end
    end
    return true
end
do
    local f=io.open(path,'rb')
    if f then
        local text=f:read('*a');f:close()
        local candidate=defaults();local okay=true;local legacy;local explicit={}
        for line in (text or ''):gmatch('[^\r\n]+')do
            local key,value=line:gsub('^\239\187\191',''):match('^%s*([%w_]+)%s*=%s*(.-)%s*$')
            if key=='max_charges' then
                legacy=tonumber(value);if not number(legacy,1,10,1)then okay=false end
            elseif type(candidate[key])=='boolean' then
                if value~='0' and value~='1'then okay=false else candidate[key]=value=='1'end
            elseif type(candidate[key])=='number' then candidate[key]=tonumber(value);explicit[key]=true end
        end
        if legacy then
            for _,group in ipairs{'green','blue'}do
                local key=group..'_max_charges';if not explicit[key]then candidate[key]=legacy end
            end
        end
        if okay and validate(candidate)then config=candidate;S.config=config
        else config.enabled=false;note('Invalid configuration; feature disabled; repair using MODS')end
    else
        local okay,why=native.save(path,config_text(config));if not okay then note('Config creation failed: '..tostring(why))end
    end
end
local model=Model.new(native,config,note);S.model=model
local menu,menu_blocked
local function change(key,value)
    if model.stopped then return false,model.reason end
    if config[key]==nil then return false,'unknown option'end
    local candidate={};for name,current in pairs(config)do candidate[name]=current end
    candidate[key]=value
    if not validate(candidate)then return false,'invalid option value'end
    local okay,why=native.save(path,config_text(candidate));if not okay then return false,why end
    config[key]=value
    if key=='enabled' and not value then model.release('Disabled in MODS')end
    if not value and key:match('^(%w+)_enabled$') then
        model.release('Group disabled in MODS',key:match('^(%w+)_enabled$'))
    end
    note('Setting applied: '..key..'='..tostring(value));return true
end
local specs={
    {'enabled',{type='toggle',label='启用战备次数储存（总开关）',default=config.enabled,
        description='控制整个模组，仅影响本机玩家。关闭会恢复本模组仍持有的原生字段；再次启用时重新开始储存。'}},
    {'inherit_ratio',{type='toggle',label='按比例继承补充进度（三组通用）',default=config.inherit_ratio,
        description='开启保留已完成百分比；关闭保留已完成秒数（默认）。呼叫使储备减少、调整倍率或上限时，按此方式继承进度。短冷却期间暂停补充。'}},
    {'short_cooldown',{type='slider',label='短冷却时间（秒）',min=1,max=60,step=0.5,default=config.short_cooldown,
        description='成功呼叫后仍有次数时使用。沿用原生部署阶段，随后进入此短冷却；修改从下一次呼叫生效。'}},
}
local descriptions={red='仅轨道系列，不含飞鹰和任务战备。轨道激光仍受每局最多 3 次限制。',
    green='哨戒炮、地雷、炮台、防御墙、防护罩中继器和特斯拉塔。',
    blue='突击兵、荡平者、消耗性凝固汽油弹、单兵导弹发射井、子弹风暴、EAT-17、便携式地狱火背包。'}
local labels={red='红战备（轨道）',green='绿战备',blue='蓝战备（一次性装备）'}
for _,group in ipairs(groups)do
    local label=labels[group]
    specs[#specs+1]={group..'_enabled',{type='toggle',label=label..'：启用次数储存',default=config[group..'_enabled'],
        description=descriptions[group]..'关闭只恢复该组，重新启用后重新开始储存。'}}
    specs[#specs+1]={group..'_max_charges',{type='slider',label=label..'：储存次数上限',min=1,max=10,step=1,default=config[group..'_max_charges'],
        description='只影响该组战备，每个战备独立计数。默认 3。降低上限裁掉多余次数；提高上限不会赠送次数。'}}
    specs[#specs+1]={group..'_cd_growth',{type='slider',label=label..'：储备补充冷却增长倍率（X）',min=1,max=3,step=0.1,default=config[group..'_cd_growth'],
        description='下一次补充耗时＝原冷却×倍率^(当前次数−1)。默认 1.0 不增加。1.5 时，有 1/2/3 次对应 1/1.5/2.25 倍；不影响短冷却或用尽次数后的完整冷却。'}}
end
local function checked(ok,why)assert(ok==true,tostring(why or 'menu API failed'))end
local function menu_step()
    if menu_blocked then return end
    local okay,why=pcall(function()
        if not menu then
            local api=rawget(_G,'ModOptionsMenu');if not api then return end
            assert(api.api==1 and (tonumber(api.version)or 0)>=2,'ModOptionsMenu API 1 / version 2 required')
            for _,method in ipairs{'register_option','on_change','get','set'}do assert(type(api[method])=='function','missing menu '..method)end
            for _,row in ipairs(specs)do
                local key,spec=row[1],row[2];spec.mod='战备次数储存 / Stratagem Reserve'
                if api.version>=3 then spec.mod_id='stratagem_reserve'end
                checked(api.register_option('stratagem_reserve_'..key,spec))
                checked(api.on_change('stratagem_reserve_'..key,function(value)return change(key,value)end))
            end
            menu=api;S.menu_registered=true;note('MODS menu registered')
        end
        for _,row in ipairs(specs)do
            local key=row[1];local id='stratagem_reserve_'..key
            if menu.get(id)~=config[key]then checked(menu.set(id,config[key]))end
        end
    end)
    if not okay then menu_blocked=true;S.menu_error=tostring(why);note('Menu unavailable: '..S.menu_error)end
end
local previous_update=rawget(_G,'update');local previous_shutdown=rawget(_G,'shutdown')
if type(previous_update)~='function'then model.stop('game update unavailable');S.phase='stopped';return S end
local pending=false;local recovering=false;local frames=120
local function after(...)
    if not recovering then
        local okay,why=pcall(model.tick)
        if not okay then model.stop(why)end
    end
    pending=false;recovering=false
    S.phase=model.stopped and 'stopped' or (config.enabled and 'active' or 'disabled')
    return ...
end
rawset(_G,'update',function(...)
    if pending then
        recovering=true;model.release('Previous update failed; restoring before retry')
        note('Previous game/mod update error was propagated')
    end
    frames=frames+1;if frames>=120 then frames=0;menu_step()end
    pending=true
    -- The original update stays outside pcall: arguments, returns and errors pass through.
    return after(previous_update(...))
end)
rawset(_G,'shutdown',function(...)
    model.release('Shutdown')
    if logfile then pcall(function()logfile:close()end);logfile=nil end
    if type(previous_shutdown)=='function'then return previous_shutdown(...)end
end)
if type(jit)=='table' and type(jit.off)=='function'then
    for _,module in ipairs{native,model}do for _,fn in pairs(module)do if type(fn)=='function'then pcall(jit.off,fn,true)end end end
    pcall(jit.off,after,true)
end
S.phase='waiting';note('Stratagem Reserve 0.3.0 loaded; orbital/green/blue groups; awaiting mission')
return S
