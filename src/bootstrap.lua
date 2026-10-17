local S={version='0.3.3',phase='initializing',ingame_tested=false,multiplayer_tested=false}
local loader=rawget(_G,'CowboyBingusModLoader')
if type(loader)~='table' or loader.api~=1 or type(loader.open_log)~='function' then
    S.phase='stopped';S.reason='Bingus Shared Loader v18 / API 1 required'
    pcall(print,'[StratagemReserve] '..S.reason);return S
end
local logfile
pcall(function() logfile=loader.open_log('StratagemReserve.log') end)
local elapsed,last_flush=0,0
local log_times={}
local function note(line)
    S.status=tostring(line)
    local key=S.status
    if log_times[key] and elapsed-log_times[key]<30 then return end
    -- Keep diagnostics bounded even if many distinct external errors occur.
    local count=0;for k,t in pairs(log_times)do
        if elapsed-t>=30 then log_times[k]=nil else count=count+1 end
    end
    if count>=64 then return end
    log_times[key]=elapsed
    pcall(print,'[StratagemReserve] '..S.status)
    if logfile then pcall(function()logfile:write(os.date('%H:%M:%S ')..S.status..'\n')end)end
end
local native=Native.new(Targets,note);S.native=native
local groups={'red','green','blue'}
local function defaults()
    local c={language='zh',enabled=true,inherit_ratio=false,short_cooldown=5}
    for _,group in ipairs(groups)do c[group..'_enabled']=true;c[group..'_max_charges']=3;c[group..'_cd_growth']=1 end
    return c
end
local config=defaults();S.config=config
local folder=type(loader.log_directory)=='string' and loader.log_directory
    or (os.getenv('LOCALAPPDATA') or '')..'\\CowboyBingus\\Helldivers2\\Logs'
local path=folder..'\\StratagemReserve.cfg';S.config_path=path
local function config_text(c)
    local text='# Stratagem Reserve. Group caps are total callable uses.\nenabled='..(c.enabled and '1' or '0')
        ..'\nlanguage='..c.language..'\ninherit_ratio='..(c.inherit_ratio and '1' or '0')..'\nshort_cooldown='..c.short_cooldown..'\n'
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
    if c.language~='zh' and c.language~='en' then return false end
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
        local candidate=defaults();local legacy;local explicit={};local invalid={}
        for line in (text or ''):gmatch('[^\r\n]+')do
            local key,value=line:gsub('^\239\187\191',''):match('^%s*([%w_]+)%s*=%s*(.-)%s*$')
            if key=='max_charges' then
                legacy=tonumber(value);if not number(legacy,1,10,1)then legacy=nil;invalid[#invalid+1]=key end
            elseif key=='language' then
                if value=='zh' or value=='en' then candidate.language=value
                else note('Invalid language; using Chinese default')end
            elseif type(candidate[key])=='boolean' then
                if value~='0' and value~='1'then invalid[#invalid+1]=key else candidate[key]=value=='1'end
            elseif type(candidate[key])=='number' then
                local old=candidate[key];candidate[key]=tonumber(value)
                if not validate(candidate)then candidate[key]=old;invalid[#invalid+1]=key else explicit[key]=true end
            end
        end
        if legacy then
            for _,group in ipairs{'green','blue'}do
                local key=group..'_max_charges';if not explicit[key]then candidate[key]=legacy end
            end
        end
        config=candidate;S.config=config
        if #invalid>0 then
            S.config_warning=table.concat(invalid,', ')
            note('Invalid configuration fields use defaults (file preserved): '..S.config_warning)
        end
    else
        local okay,why=native.save(path,config_text(config));if not okay then note('Config creation failed: '..tostring(why))end
    end
end
local model=Model.new(native,config,note);S.model=model
local menu,menu_provider
local registered,bound={},{}
local menu_retry_at,menu_failures=0,0
local function change(key,value)
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
-- Functions are re-evaluated by ModOptionsMenu when Esc is reopened.
-- Descriptions intentionally remain bilingual in either selected language.
local function text(zh,en)
    return function()return config.language=='en' and en or zh end
end
local function description(zh,en)
    return function()return '中文：'..zh..' English: '..en end
end
local title=text('战备次数储存','Stratagem Reserve')
local specs={
    {'language',{type='choice',label='Language',choices={'简体汉字','English'},
        default=config.language=='en' and 2 or 1,
        description=description('仅切换本模组标题和选项标签；说明始终中英双语。应用后关闭并重新打开 Esc 菜单。',
            'Changes this mod title and labels only. Descriptions stay bilingual. Apply, then close and reopen Esc.')}},
    {'enabled',{type='toggle',label=text('启用战备次数储存（总开关）','Enable Stratagem Reserve (master)'),default=config.enabled,
        description=description('控制整个模组，仅影响本机玩家。关闭会恢复本模组仍持有的原生字段；再次启用时重新开始储存。',
            'Local player only. Disabling restores native fields still owned by this mod; enabling restarts storage.')}},
    {'inherit_ratio',{type='toggle',label=text('按比例继承补充进度（三组通用）','Keep refill percentage (all groups)'),default=config.inherit_ratio,
        description=description('开启保留已完成百分比；关闭保留已完成秒数（默认）。呼叫使储备减少、调整倍率或上限时，按此方式继承进度。短冷却期间暂停补充。',
            'On: keep completed percentage. Off (default): keep elapsed seconds when calling or changing caps/growth. Refill pauses during short cooldown.')}},
    {'short_cooldown',{type='slider',label=text('短冷却时间（秒）','Short cooldown (seconds)'),min=1,max=60,step=0.5,default=config.short_cooldown,
        description=description('成功呼叫后仍有次数时使用。沿用原生部署阶段，随后进入此短冷却；修改从下一次呼叫生效。',
            'Used after a successful call with charges left. Native deployment stays intact, followed by this cooldown. Changes apply to the next call.')}},
}
local descriptions={
    red={'仅轨道系列，不含飞鹰和任务战备。轨道激光仍受每局最多 3 次限制。',
        'Orbitals only; excludes Eagles and mission stratagems. Orbital Laser keeps its 3-use mission limit.'},
    green={'哨戒炮、地雷、炮台、防御墙、防护罩中继器和特斯拉塔。',
        'Sentries, mines, emplacements, barriers, shield relay and Tesla tower.'},
    blue={'突击兵、荡平者、消耗性凝固汽油弹、单兵导弹发射井、子弹风暴、EAT-17、便携式地狱火背包。',
        'Commando, Leveller, Expendable Napalm, Solo Silo, Bullet Storm, EAT-17 and Portable Hellbomb backpack.'},
}
local labels={red={'红战备（轨道）','Red (orbitals)'},green={'绿战备','Green'},blue={'蓝战备（一次性装备）','Blue (expendable equipment)'}}
for _,group in ipairs(groups)do
    local label=labels[group]
    specs[#specs+1]={group..'_enabled',{type='toggle',label=text(label[1]..'：启用次数储存',label[2]..': enable storage'),default=config[group..'_enabled'],
        description=description(descriptions[group][1]..'关闭只恢复该组，重新启用后重新开始储存。',
            descriptions[group][2]..' Disabling restores only this group; enabling restarts storage.')}}
    specs[#specs+1]={group..'_max_charges',{type='slider',label=text(label[1]..'：储存次数上限',label[2]..': charge cap'),min=1,max=10,step=1,default=config[group..'_max_charges'],
        description=description('只影响该组战备，每个战备独立计数。默认 3。降低上限裁掉多余次数；提高上限不会赠送次数。',
            'Each stratagem has its own count. Default: 3. Lower caps trim excess charges; higher caps grant no extra charges.')}}
    specs[#specs+1]={group..'_cd_growth',{type='slider',label=text(label[1]..'：储备补充冷却增长倍率（X）',label[2]..': refill cooldown growth (X)'),min=1,max=3,step=0.1,default=config[group..'_cd_growth'],
        description=description('有 1 次储备时，补充耗时等于原冷却；每多储存 1 次，再乘一次设定倍率。默认 1.0 不增加。倍率 1.5 时，有 1/2/3 次对应原冷却的 1/1.5/2.25 倍。只影响储备补充，短冷却和用尽次数后的完整冷却保持原值。',
            'Refill uses native cooldown multiplied by growth for each extra stored charge. Default 1.0. At 1.5, 1/2/3 charges use 1/1.5/2.25x native cooldown. Short and empty-reserve cooldowns stay unchanged.')}}
end
local function checked(ok,why)assert(ok==true,tostring(why or 'menu API failed'))end
local function menu_step()
    if menu and rawget(_G,'ModOptionsMenu')~=menu then
        menu=nil;menu_retry_at=0
    end
    if elapsed<menu_retry_at then return end
    local okay,why=pcall(function()
        if not menu then
            local api=rawget(_G,'ModOptionsMenu');if not api then return end
            if api~=menu_provider then
                menu_provider=api;registered={};bound={};S.menu_registered=false
            end
            assert(api.api==1 and (tonumber(api.version)or 0)>=2,'ModOptionsMenu API 1 / version 2 required')
            for _,method in ipairs{'register_option','on_change','get','set'}do assert(type(api[method])=='function','missing menu '..method)end
            for _,row in ipairs(specs)do
                local key,spec=row[1],row[2];spec.mod=title
                if tonumber(api.version)>=3 then spec.mod_id='stratagem_reserve'else spec.mod_id=nil end
                if not registered[key]then
                    checked(api.register_option('stratagem_reserve_'..key,spec));registered[key]=true
                end
                if not bound[key]then
                    checked(api.on_change('stratagem_reserve_'..key,function(value)
                    if key=='language' then
                        if value~=1 and value~=2 then return false,'invalid language choice'end
                        return change(key,value==2 and 'en' or 'zh')
                    end
                    return change(key,value)
                    end));bound[key]=true
                end
            end
            menu=api;S.menu_registered=true;note('MODS menu registered')
        end
        for _,row in ipairs(specs)do
            local key=row[1];local id='stratagem_reserve_'..key
            local wanted=config[key]
            if key=='language' then wanted=config.language=='en' and 2 or 1 end
            if menu.get(id)~=wanted then checked(menu.set(id,wanted))end
        end
    end)
    if not okay then
        menu=nil;S.menu_registered=false;menu_failures=math.min(menu_failures+1,6)
        menu_retry_at=elapsed+math.min(30,2^(menu_failures-1))
        S.menu_error=tostring(why);note('Menu unavailable; retrying: '..S.menu_error)
    else S.menu_error=nil;menu_failures=0 end
end
local previous_update=rawget(_G,'update');local previous_shutdown=rawget(_G,'shutdown')
if type(previous_update)~='function'then model.stop('game update unavailable');S.phase='stopped';return S end
local pending=false;local recovering=false;local frames=120;local frame_dt=0
local function after(...)
    if not recovering then
        local okay,why=pcall(model.tick)
        if not okay then model.stop(why)end
    end
    pending=false;recovering=false
    S.phase=not config.enabled and 'disabled' or (model.stopped and 'suspended'
        or (next(model.blocked) and 'partial' or (model.inactive and 'waiting' or 'active')))
    if logfile and elapsed-last_flush>=5 then pcall(function()logfile:flush()end);last_flush=elapsed end
    return ...
end
rawset(_G,'update',function(...)
    local dt=select(1,...)
    frame_dt=type(dt)=='number' and dt==dt and dt>=0 and dt<3600 and dt or 1/60
    elapsed=elapsed+frame_dt
    model.advance(frame_dt)
    if pending then
        recovering=true
        if not S.previous_update_failed then
            model.release('Previous update failed; restoring before retry');S.previous_update_failed=true
        else model.release()end
    end
    frames=frames+1;if frames>=120 then frames=0;menu_step()end
    pending=true
    if not recovering then S.previous_update_failed=false end
    -- The original update stays outside pcall: arguments, returns and errors pass through.
    return after(previous_update(...))
end)
rawset(_G,'shutdown',function(...)
    model.release('Shutdown',nil,true)
    if logfile then pcall(function()logfile:close()end);logfile=nil end
    if type(previous_shutdown)=='function'then return previous_shutdown(...)end
end)
if type(jit)=='table' and type(jit.off)=='function'then
    for _,module in ipairs{native,model}do for _,fn in pairs(module)do if type(fn)=='function'then pcall(jit.off,fn,true)end end end
    pcall(jit.off,after,true)
end
rawset(_G,'StratagemReserve',S)
S.phase='waiting';note('Stratagem Reserve 0.3.3 loaded; enabled='..tostring(config.enabled)..'; awaiting mission')
return S
