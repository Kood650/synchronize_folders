# Synchronize folder files

Program to synchronize files (and optionally empty directories) between two directories, source and replica. (Tested on Windows and Ubuntu22 through wsl)

## Running the program

On a command line, go to project directory and run the script:
```
python3 .\src\Syncer\sync.py <abs_path_source_folder> <abs_path_replica_folder> <abs_path_log_path.txt> <synch_interval_in_seconds>
```

Example:
```
python3 .\src\Syncer\sync.py C:\FolderA\SyncFiles\source C:\FolderB\SyncFiles\replica C:\FolderB\SyncFiles\logs\log.txt  5
```

If more info is needed run:
```
python3 .\src\Syncer\sync.py -h
```

To stop the synching interrupt the terminal (**__ SYNCHING IS PERFORMED BEFORE CLOSURE  __**).

### Option

If only interested in tracking files and not empty folders set the `class SyncFiles` instance variable `self.track_empty = True` to False.
        

### Known Issues

- [] Deleting/creating directories of empty folders can take more than one cycle. (Issue at `manageEmptyFolder` method)

