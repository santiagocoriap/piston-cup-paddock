# Server collector

The collector runs on the computer of the AC server. It sends new result files and Real Penalty logs to the app. It can also listen to the UDP plugin events.

The collector only reads. It never writes in the server folders, and it never sends a packet to the AC server. If the app is not available, the collector keeps the files and sends them later.

## Install

1. Install Python 3.11 or newer on the server computer. The collector needs no other package.
2. Copy this folder to the server computer.
3. In the app, open the championship page. In "Colectores", make a key. The app shows the key one time only.
4. Copy `collector.example.ini` to `collector.ini`. Put in the app address, the key, and the server folders.
5. Check the key:

   ```
   python paddock_collector.py --config collector.ini --check
   ```

6. Start the collector:

   ```
   python paddock_collector.py --config collector.ini
   ```

To start it with Windows, make a task in Task Scheduler that runs the command of step 6 at startup.

## What happens to a file

- A result file goes to the app about 10 seconds after the AC server writes it.
- A Real Penalty log goes to the app when a newer log starts, or after 10 minutes with no change.
- The app finds the round from the track and the time of the file. It makes an import preview. An admin still checks the preview and applies it.
- If the app finds no round, the file waits in "Colectores" on the championship page. An admin chooses the round there.
- The same file sent again adds nothing.

## UDP plugin events (optional)

Real Penalty already uses the UDP plugin connection. Content Manager can send the same events to more plugins:

1. In Content Manager, open the server preset. Go to Advanced, CM plugin, Extra plugins.
2. Add a plugin with the address `127.0.0.1:6973` (or any free port).
3. Set `udp_port = 6973` in `collector.ini`.

The collector records session starts and ends, connections, laps, and collisions. It accepts packets only from the same computer.
