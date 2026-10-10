local existing=rawget(_G,'StratagemReserve')
if existing then return existing end
local S={version='0.1.0',phase='initializing',ingame_tested=false,multiplayer_tested=false}
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
local config={enabled=true,max_charges=3,short_cooldown=5};S.config=config
local folder=type(loader.log_directory)=='string' and loader.log_directory
    or (os.getenv('LOCALAPPDATA') or '')..'\\CowboyBingus\\Helldivers2\\Logs'
local path=folder..'\\StratagemReserve.cfg';S.config_path=path
local function config_text(c)
    return '# EAT-17 experiment. max_charges is total callable uses.\nenabled='..(c.enabled and '1' or '0')
        ..'\nmax_charges='..c.max_charges..'\nshort_cooldown='..c.short_cooldown..'\n'
end
local function validate(c)
    return type(c.enabled)=='boolean' and type(c.max_charges)=='number' and c.max_charges%1==0
        and c.max_charges>=1 and c.max_charges<=10 and type(c.short_cooldown)=='number'
        and c.short_cooldown==c.short_cooldown and c.short_cooldown>=1 and c.short_cooldown<=60
        and c.short_cooldown*2%1==0
end
do
    local f=io.open(path,'rb')
    if f then
        local text=f:read('*a');f:close()
        local candidate={enabled=true,max_charges=3,short_cooldown=5};local okay=true
        for line in (text or ''):gmatch('[^\r\n]+')do
            local key,value=line:gsub('^\239\187\191',''):match('^%s*([%w_]+)%s*=%s*(.-)%s*$')
            if key=='enabled' then
                if value~='0' and value~='1'then okay=false else candidate.enabled=value=='1'end
            elseif key=='max_charges' or key=='short_cooldown'then candidate[key]=tonumber(value)end
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
    local candidate={enabled=config.enabled,max_charges=config.max_charges,short_cooldown=config.short_cooldown}
    candidate[key]=value
    if not validate(candidate)then return false,'invalid option value'end
    local okay,why=native.save(path,config_text(candidate));if not okay then return false,why end
    config[key]=value
    if key=='enabled' and not value then model.release('Disabled in MODS')end
    note('Setting applied: '..key..'='..tostring(value));return true
end
local specs={
    {'enabled',{type='toggle',label='启用 EAT-17 次数储存',default=config.enabled,
        description='实验版，仅影响本机玩家的 EAT-17。关闭会恢复本模组仍持有的原生字段。'}},
    {'short_cooldown',{type='slider',label='有剩余次数时的冷却（秒）',min=1,max=60,step=0.5,default=config.short_cooldown,
        description='成功呼叫后仍有次数时使用。沿用原生部署阶段，随后进入此短冷却；修改从下一次呼叫生效。'}},
    {'max_charges',{type='slider',label='可储存的总次数上限',min=1,max=10,step=1,default=config.max_charges,
        description='右下角显示几次，就能呼叫几次。默认 3。降低上限会裁掉多余次数；提高上限不会赠送次数。'}},
}
local function checked(ok,why)assert(ok==true,tostring(why or 'menu API failed'))end
local function menu_step()
    if menu_blocked then return end
    local okay,why=pcall(function()
        if not menu then
            local api=rawget(_G,'ModOptionsMenu');if not api then return end
            assert(api.api==1 and (tonumber(api.version)or 0)>=2,'ModOptionsMenu API 1 / version 2 required')
            for _,method in ipairs{'register_option','on_change','get','set'}do assert(type(api[method])=='function','missing menu '..method)end
            for _,row in ipairs(specs)do
                local key,spec=row[1],row[2];spec.mod='战备次数储存 / EAT-17 实验'
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
S.phase='waiting';note('Stratagem Reserve 0.1.0 loaded; EAT-17 only; awaiting mission')
return S
