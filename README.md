app to automatically push to the selected repo after every save/compile (depending on the file)

- 'Path To Watch' is the local directory where you want to monitor the file change
- 'Git Repository' will find the remote repo in the .git directory. This will usually be the same as the Path To Watch
- 'File To Watch' is the file type you want to watch for a change.
    - for A/V usage, this is usually when a qsys file gets saved, or a crestron file compiles.
- 'Default Remote' - defaults to origin
- 'Default Branch' - defaults to main

- Start Monitoring will start the process to monitor the file
  - if the file changes, the app will show a popup to add a commit message and a button to push or cancel the process
- Stop Monitoring will stop the monitoring. This can allow you to change the directories without closing and reopening the app
- Minimize to Tray will minimize the app to the task bar tray.
    - right click to show more quick actions
 
    - Quick Actions (when minimized)
      - reopen the config window
      - force a push
      - pull
      - fetch
      - exit
