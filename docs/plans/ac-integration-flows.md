# How the AC integration works

Date: October 14, 2026

These diagrams show the plan in `docs/plans/ac-integration.md` when all phases are done. Phase 0 confirmed that the Paddock script idea works.

| Word | Meaning |
| --- | --- |
| Paddock app | The website of the league. It keeps results, standings, and laps. |
| Server program | paddock-collector.exe. It runs on the PC of the AC server. It sends files and events to the app, and writes the race setup into the server. |
| Paddock script | A small Lua script. The league server sends it into AC when a driver joins. It runs inside the game and sends each lap to the app. |
| Key | A secret password for the server program. The app shows it one time only. |
| Race code | A new secret for each race. The app makes it, the server gives it to the drivers on the server, and the script sends it with each lap. |
| CSP | Custom Shaders Patch. A free add-on for AC. The league server already needs it. |

## 0. The whole system in one picture

The boxes are the places where things run. The arrows show what goes where. Only the admin clicks one button. All other arrows happen by themselves.

```mermaid
flowchart TB
    subgraph SERVERPC["PC of the AC server"]
        AC["AC server"]
        RP["Real Penalty"]
        SC["Server program<br/>paddock-collector.exe"]
        FILES[("Server files<br/>entry_list.ini<br/>server_cfg.ini<br/>csp_extra_options.ini")]
    end
    subgraph DRIVERPC["PC of each driver"]
        GAME["AC with CSP"]
        PS["Paddock script<br/>runs inside AC"]
    end
    subgraph CLOUD["The internet"]
        APP["Paddock app<br/>the league website"]
    end
    ADMIN(["Admin"])
    DRIVER(["Driver"])

    ADMIN -- "clicks 'Enviar al servidor'" --> APP
    APP -- "race setup and race code" --> SC
    SC -- "writes before the race" --> FILES
    FILES -- "AC reads at start" --> AC
    AC -- "live events" --> SC
    AC -- "result file" --> SC
    RP -- "penalty log" --> SC
    SC -- "files and events" --> APP
    DRIVER -- "joins the server" --> GAME
    GAME <-- "race" --> AC
    AC -- "sends the script address" --> GAME
    GAME -- "starts by itself" --> PS
    PS -- "each lap" --> APP
    APP -- "results, standings, telemetry" --> DRIVER
```

## 1. Admin: connect the AC server to the app

The admin does this one time. After this, the server program starts by itself with Windows.

```mermaid
flowchart TD
    A([Start: the admin wants the server to talk to the app]) --> B["In the app, turn on 'Modo admin'"]
    B --> C["Open the championship page, then 'Colectores'"]
    C --> D["Click 'Crear clave'.<br/>The key is a secret password for the server PC"]
    D --> E["Click 'Descargar colector'.<br/>You get a zip: the program + a settings file with the key inside"]
    E --> F["Copy the zip to the PC that runs the AC server, and unzip it"]
    F --> G["Run paddock-collector.exe --setup"]
    G --> H["The program asks 2 things:<br/>1. Where is the AC server folder?<br/>2. What is the public address and port of the server?"]
    H --> I{"The program calls the app:<br/>'Is my key good?'"}
    I -- No --> J["The screen says what is wrong.<br/>Fix the key or the address"]
    J --> G
    I -- Yes --> K["Run paddock-collector.exe --install.<br/>Now it starts by itself with Windows"]
    K --> L["In Content Manager, add the extra plugin 127.0.0.1:6973.<br/>Now the program hears the race live"]
    L --> M["In collector.ini set write_server_config = true.<br/>The program can now write the race setup<br/>and the Paddock script into the server"]
    M --> N(["Done. In 'Colectores' the server shows a green dot: 'Conectado'"])
```

## 2. Driver: what you do

The driver installs nothing new and opens nothing. Nobody must remember to start a program.

```mermaid
flowchart TD
    A([Start: an admin sends you an invite link]) --> B["Open the link. Choose your password"]
    B --> C["The admin puts your Steam ID on your driver profile.<br/>It tells the app which car on the server is you"]
    C --> D{"Do you have Content Manager<br/>and CSP in AC?"}
    D -- No --> E["Install them one time.<br/>The league server needs them anyway"]
    E --> F
    D -- Yes --> F["In 'Mi cuenta', choose who sees your laps"]
    F --> G(["Done. You install nothing more and open nothing more"])
    G --> H["Race night: join the league server in AC, as always"]
    H --> I["AC gets the Paddock script from the server by itself<br/>and runs it inside the game"]
    I --> J["A small line in AC says:<br/>'Paddock: Fecha 3 · Carrera · grabando'"]
    J --> K["Drive. Each lap goes to the app by itself"]
    K --> L(["Leave the server. The script stops by itself"])
```

## 3. Race night: who talks to whom

This happens on each race night. Read it from top to bottom. The arrows show who sends what to whom.

```mermaid
sequenceDiagram
    autonumber
    actor Admin
    participant App as Paddock app
    participant SC as Server program<br/>(next to AC server)
    participant AC as AC server
    participant PS as Paddock script<br/>(inside AC of each driver)
    actor Driver

    Note over Admin,App: Before the race
    Admin->>App: Draw the conditions. The app knows each ballast and restrictor
    Admin->>App: Click "Enviar al servidor"
    App->>App: Make a new race code
    SC->>App: Every 30 s: "Is there work for me?"
    App-->>SC: Yes: entry list, weather, track, race code
    SC->>SC: Is the AC server stopped? Save a copy of the old files
    SC->>AC: Write entry_list.ini, server_cfg.ini, csp_extra_options.ini
    SC-->>App: Done
    Admin->>AC: Start the AC server

    Note over AC,Driver: The race
    Driver->>AC: Join the server in AC
    AC-->>PS: Here is the script address and the race code
    PS->>PS: AC downloads the script and starts it. No click
    AC-->>SC: Live: new session, driver connected with Steam ID
    SC-->>App: Session started. Drivers on the server
    PS->>App: "What runs now?"
    App-->>PS: Fecha 3, race
    PS-->>Driver: Line in AC: Paddock grabando
    loop Each lap
        PS->>App: Lap with speed, pedals, Steam ID, race code
        App->>App: Right code? Steam ID on the server now? Then it is a league lap
    end
    AC-->>SC: Live: crashes, laps, disconnects

    Note over AC,App: After the race
    AC->>SC: Writes the result file. Real Penalty writes its log
    SC->>App: Send the result file and the log
    App->>App: Find the round. Check the file
    alt No problems
        App-->>Admin: Provisional result is published. Drivers get a notice
    else A problem
        App-->>Admin: "Revisar importación" in your to-do list
    end
    Admin->>App: Approve the official result
```

## 4. Is this lap a league lap?

The app asks these questions for each lap. Only a lap with 'yes' to all questions counts for the league.

```mermaid
flowchart TD
    A([A lap comes to the app]) --> B{"Did the Paddock script send it,<br/>with the race code of tonight?"}
    B -- "No, it came from the practice app" --> P
    B -- "No, old or wrong code" --> X
    B -- Yes --> D{"Was a league session running<br/>at that time?"}
    D -- "Not yet known" --> W["Wait. Check again when<br/>the server data comes"]
    W --> D
    D -- No --> X
    D -- Yes --> E{"Does the server say that this Steam ID<br/>was connected then?"}
    E -- No --> X
    E -- Yes --> F{"Same track and same car?"}
    F -- No --> X
    F -- Yes --> L(["LEAGUE LAP<br/>Goes to the round, the session, and the attempt"])
    P(["PRACTICE LAP<br/>Private. Only the driver sees it"])
    X(["NOT KEPT<br/>The app does not store it"])
```

## How the app trusts a lap

1. The lap has the race code of tonight. Only drivers on the league server get this code.
2. The server program says that this Steam ID was on the server at that time.
3. The lap time is inside a league session, and the track and the car are the same.
4. If one point fails, the app does not keep the lap.

## The work plan

| Phase | Days | What it gives |
| --- | --- | --- |
| 0. Test the script idea | 0.5 | Check that the server script runs by itself, can send to the app, and can read the Steam ID. |
| 1. Publish clean imports | 1 | A result file with no problems becomes a provisional result with no admin click. |
| 2. Session sync and the script | 2.5 | The app stores each server session and who was on it. The Paddock script sends the laps. |
| 3. Conditions and disconnects | 1 | The app reads the weather from the server. A disconnect gives a DNF suggestion. |
| 4. Send the setup to the server | 2 | 'Enviar al servidor' writes the entry list, ballast, restrictor, weather, and the race code. |
| 5. Install with one click | 1 | The server program becomes an .exe that starts with Windows and updates itself. |
| 6. Health and alerts | 0.5 | The app warns the admins when a collector stops or a race night has no results. |
