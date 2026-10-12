# Current scripts

These scripts are the league's earlier tools. They are reference material only. They are not part of the app.

Use them for ideas about design and wanted features. Copy a useful piece into the app only after a review.

- `generate_report.py` makes an HTML race report from a result file and a Real Penalty log.
- `live_logger.py` records car positions, laps, and collisions through the AC UDP plugin protocol.
- `render_replay.py` makes an HTML position replay from the `live_logger.py` output.

Known problem: `live_logger.py` accepts UDP packets from any address. Do not copy that part as it is.
