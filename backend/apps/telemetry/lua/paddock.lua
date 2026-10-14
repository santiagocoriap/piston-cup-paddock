-- Paddock script.
--
-- The league server lists this script in its CSP options, with the race code of the
-- championship. AC downloads the script when a driver joins and runs it inside the game: the
-- driver installs nothing and opens nothing. At the end of each lap, the script sends the lap
-- to the Paddock app, also a lap with track cuts. The app takes the lap number and the cuts
-- from the server, not from CSP. The app keeps the lap only when the server collector says that this
-- driver was on the server at that time (docs/plans/ac-integration.md, phase 2).
--
-- The app writes its own address into PADDOCK_URL when it gives the script to CSP.

local PADDOCK_URL = '__PADDOCK_URL__'
local SAMPLE_EVERY = 0.05 -- seconds, so 20 samples each second
local MAX_QUEUE = 30 -- laps that wait when the internet is down
local RETRY_AFTER = 15 -- seconds

local car = ac.getCar(0)
local sim = ac.getSim()
local steamID = ac.getUserSteamID()
local settings = ac.configValues({ raceCode = '' })
local headers = { ['Content-Type'] = 'application/json', ['X-Paddock-Code'] = settings.raceCode }

local samples = {}
local sinceSample = 0
local queue = {}
local sending = false
local retryAt = 0
local status = 'Paddock: conectando'
local label = ''

local function setStatus(text)
  status = 'Paddock: ' .. text
end

local function askNow()
  web.get(PADDOCK_URL .. '/api/script/now', headers, function(err, response)
    if (err and err ~= '') or response.status ~= 200 then
      setStatus('sin conexión')
      return
    end
    local now = JSON.parse(response.body) or {}
    label = now.label or ''
    setStatus(label ~= '' and (label .. ' · grabando') or 'grabando')
  end)
end

-- CSP allows two web requests at the same time. The script sends one lap at a time, in order.
local function pump()
  if sending or #queue == 0 or os.preciseClock() < retryAt then return end
  local item = queue[1]
  item.sent_at = os.time()
  sending = true
  web.post(PADDOCK_URL .. '/api/script/laps', headers, JSON.stringify(item), function(err, response)
    sending = false
    if (err and err ~= '') or response.status >= 500 then
      retryAt = os.preciseClock() + RETRY_AFTER
      setStatus('sin conexión, la vuelta espera')
      return
    end
    table.remove(queue, 1)
    if response.status == 200 then
      local answer = JSON.parse(response.body) or {}
      if answer.state == 'rejected' then
        setStatus('esta vuelta no cuenta para la liga')
      elseif answer.state == 'pending' then
        setStatus('vuelta enviada, espera los datos del servidor')
      else
        local text = 'vuelta ' .. tostring(answer.lap_number or '') .. ' guardada'
        if answer.cuts and answer.cuts > 0 then
          text = text .. ' (' .. tostring(answer.cuts) .. (answer.cuts == 1 and ' corte)' or ' cortes)')
        end
        setStatus((label ~= '' and (label .. ' · ') or '') .. text)
      end
    else
      setStatus('vuelta rechazada (' .. tostring(response.status) .. ')')
    end
  end)
end

askNow()
ac.onSessionStart(function()
  samples = {}
  askNow()
end)

ac.onLapCompleted(0, function(carIndex, lapTime, valid, cuts, lapCount)
  if #samples > 0 then
    if #queue >= MAX_QUEUE then table.remove(queue, 1) end
    table.insert(queue, {
      steam_id = steamID,
      track = ac.getTrackID(),
      layout = ac.getTrackLayout(),
      car = ac.getCarID(0),
      lap_number = lapCount,
      lap_time_ms = lapTime,
      valid = valid,
      cuts = cuts,
      ended_at = os.time(),
      samples = samples,
    })
  end
  samples = {}
end)

function script.update(dt)
  sinceSample = sinceSample + dt
  if sinceSample >= SAMPLE_EVERY then
    sinceSample = 0
    samples[#samples + 1] = {
      car.lapTimeMs,
      math.floor(car.splinePosition * 100000) / 100000,
      math.floor(car.speedKmh * 10) / 10,
      math.floor(car.gas * 1000) / 1000,
      math.floor(car.brake * 1000) / 1000,
      math.floor(car.steer * 10) / 10,
      car.gear,
      math.floor(car.rpm),
    }
  end
  pump()
end

function script.drawUI()
  ui.dwriteDrawText(status, 13, vec2(16, sim.windowHeight - 28), rgbm(1, 1, 1, 0.6))
end
