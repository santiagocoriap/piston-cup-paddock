-- Paddock script, phase 0 test.
--
-- The league server lists this file in its CSP options. CSP downloads it when a driver joins and
-- runs it inside AC. The test checks 4 points: the script starts with no driver action, it can
-- send a web request, it can read the Steam ID, and it does not slow the game.
--
-- PADDOCK_URL is the address of the test receiver (collector/script/test_receiver.py).

local PADDOCK_URL = 'http://127.0.0.1:8765'
local SAMPLE_EVERY = 0.05 -- seconds, so 20 samples each second

local car = ac.getCar(0)
local sim = ac.getSim()
local steamID = ac.getUserSteamID()
-- Values from the [SCRIPT_...] section of the server. The race code comes from the app.
local settings = ac.configValues({ raceCode = '' })

local samples = {}
local sinceSample = 0
local updateCost = 0 -- seconds spent in script.update since the last lap
local updateCalls = 0
local fpsSum = 0
local queue = {} -- payloads that wait to go to the receiver
local sending = false

local function post(path, payload)
  table.insert(queue, { path = path, body = JSON.stringify(payload) })
end

-- CSP allows two requests at the same time. Send one at a time, in order.
local function pump()
  if sending or #queue == 0 then return end
  local item = table.remove(queue, 1)
  sending = true
  web.post(PADDOCK_URL .. item.path, { ['Content-Type'] = 'application/json' }, item.body, function(err, response)
    sending = false
    if err and err ~= '' then
      ac.setSystemMessage('Paddock test', 'Send failed: ' .. tostring(err))
      table.insert(queue, 1, item) -- Try again later.
    elseif response.status ~= 200 then
      ac.setSystemMessage('Paddock test', 'Receiver answered ' .. tostring(response.status))
    end
  end)
end

post('/hello', {
  steamID = steamID,
  raceCode = settings.raceCode,
  serverName = ac.getServerName(),
  serverIP = ac.getServerIP(),
  serverPortTCP = ac.getServerPortTCP(),
  track = ac.getTrackID(),
  layout = ac.getTrackLayout(),
  car = ac.getCarID(0),
  isOnlineRace = sim.isOnlineRace,
  sessionType = sim.raceSessionType,
})
ac.setSystemMessage('Paddock test', 'Script started. Steam ID: ' .. tostring(steamID))

ac.onLapCompleted(0, function(carIndex, lapTime, valid, cuts, lapCount)
  post('/lap', {
    steamID = steamID,
    lapCount = lapCount,
    lapTimeMs = lapTime,
    valid = valid,
    cuts = cuts,
    sampleCount = #samples,
    samples = samples,
    avgUpdateMs = updateCalls > 0 and (updateCost / updateCalls * 1000) or 0,
    avgFps = updateCalls > 0 and (fpsSum / updateCalls) or 0,
  })
  samples = {}
  updateCost, updateCalls, fpsSum = 0, 0, 0
end)

function script.update(dt)
  local started = os.preciseClock()
  sinceSample = sinceSample + dt
  if sinceSample >= SAMPLE_EVERY then
    sinceSample = 0
    samples[#samples + 1] = {
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
  updateCost = updateCost + (os.preciseClock() - started)
  updateCalls = updateCalls + 1
  fpsSum = fpsSum + sim.fps
end
