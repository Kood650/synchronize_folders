import os
import sys
import hashlib
import json
import shutil
import time
import logging
import argparse
import signal
"""Sync project
    -One way sync:
        *Assumed file and folder structure is required
        *Assumed nefarious interations with source folder(deleting index of files creates \
            a new one and gives it to replica folder) replica foulder (deleting the entire folder \
            or everything except index still manages to copy all file and folder content from source )
    -File creation/copying/removal operations should be logged to a file and to the
    console output;
    -Folder paths, synchronization interval and log file path should be provided
    using the command line arguments;
        * Assumed correct inputs from users, log path should not be replica or source

-Things to take into account (between source and replica folder):
    file properties (name (alias), size/hash (contents), path(location)):
    Identical files:
        Shouldnt be overwritten.
    Updated files:
        Files with same name(alias) and different hash, should be replaced
    Deleted files:
        If file in replica no longer exists in source

Implementation:
Made 2 syncer objects who map the directory every x secs and record an index of files present in directory:
    If first time running the script create the index from scratch (if on orig the index will be copied to replica ) 
        else load the available index file (applies to both)
    Update the indexes if loaded from file
        Does a walk in each directory and checks files to see if:
            file name and modification time to see if hashing is needed
            all files in index still exist
            Doesnt track index file
        Next Compare index file hash integrity and data already loaded (a bit redundat, 
            should only need to check one, unless index file is changed mid operation UPDATE: Commented hash integrity out)
        If either of them are different compare loaded indexes and check what files need to be added/updated/removed
        reloop
NOTE: KEEPING TRACK OF EMPTY FOLDERS IMPACTS THE PERFORMANCE IF THERE IS DIRECTORIES FULL OF IT
        TRACKING Empty Folders can be switched off at SyncFiles class self.track_empty = False
"""

class SyncFiles:
    def __init__(self, args) -> None:
        #TODO: use default values if user hasnt given them
        #TODO: implement exceptions for user input
        self.origin_path = r'{}'.format(args[0])
        self.log_str = args[1]
        self.master = args[2]
        self.index_str = "index.json"
        self.index = {}
        self.track_empty = True
         
    def hashFile(self, file_name, block_size=65536) -> str:
        """ Hashes file content"""
        # md5 would be faster but there would be a chance for having collision in files
        # shouldnt be a problem either way because we use file name as key comparison then the hash
        hash_sha1 = hashlib.sha1()
        with open(file_name, 'rb') as byte_file:
            block = byte_file.read(block_size)
            while len(block) > 0:
                hash_sha1.update(block)
                block = byte_file.read(block_size)
        return hash_sha1.hexdigest()

    def initSyncFolders(self, sync_from_index = False, other = None):
        """ 
            Setup process for initialization of the syncer,
        """
        if not os.path.isfile(os.path.join(self.origin_path, self.index_str)):
            os.makedirs(os.path.dirname(os.path.join(self.origin_path, self.index_str)), exist_ok = True)
            logger.info(f"CREATED {self.index_str} FILE AT {self.origin_path}")
            self.createIndex(other)
            self.saveIndex()
            # if origin index doesnt exist its because:
            # a) just started the syncing
            # b) someone deleted the index file on purpose
            if (other is not None) and self.master:
                os.makedirs(os.path.dirname(os.path.join(other.origin_path, other.index_str)), exist_ok = True)
                logger.info(f"UPDATED {other.index_str} FROM {self.origin_path} TO {other.origin_path}")
                self.export(os.path.join(self.origin_path, self.index_str),
                            os.path.join(other.origin_path, other.index_str))
                other.loadIndex()
        else:
            if sync_from_index:
                # I only want to load from index when program starts, else just use the data available 
                self.loadIndex()
            self.updateIndex(other)
            self.saveIndex()

    def createIndex(self, other = None):
        """ Goes on a walk through the directory where syncer object is created.
            gets file information and creates a dict of the files present with their metadata
            hashfile content, modified time
            (doesnt include index)
        """
        #TODO: implement walking algorithm to also get modification time during transversal of tree folder
        index = {}
        # os walk also gives folders
        origin_elem = os.walk(self.origin_path)
        #Initiation
        for dir_paths, __, file_name_list in origin_elem:
            for file in file_name_list:
                abs_path = os.path.join(dir_paths, file)
                rel_path = os.path.relpath(abs_path, self.origin_path)
                file_hash = self.hashFile(abs_path)
                modified_time = os.path.getmtime(abs_path)            
                index[rel_path] = [file_hash, modified_time]
            
            # KEEPS TRACK OF EMPTY FOLDERS, Modify self.track_empty to False to not track this
            if other and not (os.listdir(dir_paths)) and self.track_empty:
                self.manageEmptyFolder(other, dir_paths)
                            
        self.index = index
        # Dont track the index, as hashing its content would then change its own hash (inf loop)
        # This can be reformated to accept a list of ignored files
        if self.index_str in self.index:
            self.index.pop(self.index_str)

    def manageEmptyFolder(self, other, dir_paths):
        """ Helper function to create/delete empty folders between 2 syncer objects
            used while going through os.walk to see if current folder is empty, if it is
            check if caller is source folder(master) or replica (not master)
            TODO: A bit slow in deleting nested empty folders, set self.track_empty = False to not track
        """
        rel_path = os.path.relpath(dir_paths, self.origin_path)
        abs_other_path_folder = os.path.join(other.origin_path, rel_path)
        empty_folder_exists_in_other = os.path.isdir(abs_other_path_folder)
        #implement empty folder in replica if it doesnt exist
        if not(empty_folder_exists_in_other):
            # Goes into this condition if we are updating origin
            if self.master:
                logger.info(f"CREATED AN EMPTY FOLDER IN REPLICA: {abs_other_path_folder} FOUND IT IN: {dir_paths}")
                os.makedirs(abs_other_path_folder)
            # Goes into this condition if we are updating replica
            else:
                logger.info(f"DELETED AN EMPTY FOLDER IN REPLICA: {dir_paths} NOT FOUND IN: {abs_other_path_folder}")
                os.rmdir(dir_paths)
        
            
    
    def updateIndex(self, other):
        """Only use after creating an Index""" 
        missing_index = self.index.copy()
        origin_elem = os.walk(self.origin_path)
        for dir_paths, __, file_name_list in origin_elem:
            for file in file_name_list:
                abs_path = os.path.join(dir_paths, file)
                rel_path = os.path.relpath(abs_path, self.origin_path)
                modified_time = os.path.getmtime(abs_path)
                
                # Check if file is already tracked in index and if it is check if it wasnt modified using the timestamp
                if rel_path in self.index:
                    missing_index.pop(rel_path)
                    if self.index[rel_path][1] == modified_time:
                        pass
                    else:
                        # File was changed, needs a rehash
                        file_hash = self.hashFile(abs_path)
                        self.index[rel_path] = [file_hash, modified_time]    
                else:
                    # new File has been added
                    file_hash = self.hashFile(abs_path)
                    self.index[rel_path] = [file_hash, modified_time]
            
            # KEEPS TRACK OF EMPTY FOLDERS, CAN BE COMMENTED OUT TO INCREASE SPEED(Do the same on createIndex)
            if other and not (os.listdir(dir_paths)) and self.track_empty:
                self.manageEmptyFolder(other, dir_paths)
                    
        # remove index file from the index dict
        if self.index_str in self.index:
            self.index.pop(self.index_str)

        # remove entries in the dict that are no longer found in directory,
        if missing_index:
            for key in missing_index.keys():
                self.index.pop(key)

       
    def compareIndexes(self, other__index, opt_add_update = True) -> dict:
        """ Compares the objects dicts and returns dicts with the files not in common
            Delete(default):
            list the keys from other dict that is not present origin dict 
            opt_add_update
            returns dicts with the keys from self dict that is not present in other dict or have diff value
            """
        diff_dict = {}
        same_dict = {}
        update_dict = {}
        if self.index:
            for this_key in self.index.keys():
                try:
                    #check to see if file is present in the other index
                    other__index[this_key]
                except:
                    #key is not in index
                    diff_dict[this_key] = [self.index[this_key]]
                else:
                    if opt_add_update:
                        if other__index[this_key][0] != self.index[this_key][0]:
                            update_dict[this_key] = self.index[this_key]
                        else:
                            same_dict[this_key] = self.index[this_key]
        return diff_dict, same_dict, update_dict
                       
    def saveIndex(self):
        """Save index of invoked syncer"""
        with open(os.path.join(self.origin_path, self.index_str), "w", encoding='utf-8') as index_file:
            json.dump(self.index, index_file, ensure_ascii=False, indent=4)

    def loadIndex(self):
        """Load index of invoked syncer"""
        with open(os.path.join(self.origin_path, self.index_str), 'r') as index_file:
            self.index = json.load(index_file)
            
    def export(self, file_path, export_path):
        """ Manually do export of a file to a specific location """
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        shutil.copy2(file_path, export_path)
        
    def export_use_object(self, other, opt_index = None, operation = "Not Selected"):
        """Exports files inside invoked syncer index or provided index to the replica syncer """
        if opt_index is None:
            opt_index = self.index
        for file in opt_index.keys():
            logger.info(fr"{operation} FILE FROM {self.origin_path}\{file} TO {other.origin_path}\{file}")
            os.makedirs(os.path.dirname(os.path.join(other.origin_path, file)), exist_ok = True)
            shutil.copy2(os.path.join(syncer_ori.origin_path, file), os.path.join(other.origin_path, file))
 
    def delete_unindexed_files(self, index):
        for file in index.keys():
            logger.info(fr"DELETED FILE: {self.origin_path}\{file}, NOT FOUND IN SOURCE")
            os.remove(os.path.join(self.origin_path, file))
   


def signal_handler(sig, frame):
    logging.info("Interrupt Program Call Receive, Syncing And Ending")
    Orchestration(syncer_ori, syncer_repo, sync_from_index= False)
    sys.exit(0)
    

def Orchestration(syncer_ori, syncer_repo, sync_from_index):
        loop_time = time.time()
        syncer_ori.initSyncFolders(sync_from_index, other = syncer_repo)
        syncer_repo.initSyncFolders(sync_from_index, other = syncer_ori) 
        
        # Checking if tracked files were changed (both in origin and repo) and if hashes match
        sync_needed_file_integrity = syncer_ori.index != syncer_repo.index
        # sync_needed_hash_integrity = syncer_ori.hashFile(os.path.join(syncer_ori.origin_path, syncer_ori.index_str)) != \
        #     syncer_repo.hashFile(os.path.join(syncer_repo.origin_path, syncer_repo.index_str))
        
        if sync_needed_file_integrity:
            logger.debug('File diff found')
            # compares two indexes of files and return their diff, equal and the files that have been updated
            index_diff, index_equal, index_update = syncer_ori.compareIndexes(syncer_repo.index)

            # no need to compare files which were already compared
            if index_equal:
                for key in index_equal:
                    syncer_repo.index.pop(key, None)
                        
            # returns the file present in replica but not in source (these should be deleted)
            index_diff_delete, __, __ = syncer_repo.compareIndexes(syncer_ori.index, opt_add_update = False)
            # delete files not present in current workflow
            syncer_repo.delete_unindexed_files(index_diff_delete)
            # updates/add to repo and overwrite index in replica
            syncer_ori.export_use_object(syncer_repo, opt_index = index_diff, operation = "CREATED")
            syncer_ori.export_use_object(syncer_repo, opt_index = index_update, operation = "UPDATED")
            # updates the index
            syncer_ori.export(os.path.join(syncer_ori.origin_path, syncer_ori.index_str), \
                    os.path.join(syncer_repo.origin_path, syncer_repo.index_str))
        logger.info("Sync happened and took {} secs to check/apply changes".format(time.time()-loop_time))
    

if __name__ == "__main__":
    debug = False
    if debug:
        log_path = r"C:\Users\AndreM\Desktop\SharedFiles\SyncFiles\src\log.txt"
        inputArg_ori = [r"C:\Users\AndreM\Desktop\SharedFiles\SyncFiles\orig", log_path, True]
        inputArg_repo = [r"C:\Users\AndreM\Desktop\SharedFiles\SyncFiles\repl", log_path, False]
        sync_timer = 3

    else:
        #get arguments from cmdl
        parser = argparse.ArgumentParser(description = " synchronizes two folders: source and replica \
            maintaining a full, identical copy of source folder at replica folder")
        parser.add_argument("source_folder", help = "source folder of files to replicate")
        parser.add_argument("replica_folder", help = "replica folder where source files will go")
        parser.add_argument("log_path", help = "where log will go")
        parser.add_argument("synch_interval", help = " how long (in seconds) between synchronizations")
        cmdl_args = parser.parse_args()
        
        __, log_str = os.path.split(cmdl_args.log_path)
        log_path = cmdl_args.log_path
        sync_timer =  cmdl_args.synch_interval
        # Last boolean we are assigning is to declate who is original foulder and replica
        inputArg_ori = [cmdl_args.source_folder, log_str, True]
        inputArg_repo = [cmdl_args.replica_folder, log_str, False]

    # Start Syncer of the source folder and replica folder
    syncer_ori = SyncFiles(inputArg_ori)
    syncer_repo = SyncFiles(inputArg_repo)
    
    #Start logging
    os.makedirs(os.path.dirname(log_path), exist_ok = True)
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)-15s %(levelname)-8s %(message)s',
        datefmt='%a, %d %b %Y %H:%M:%S', 
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)])
    logger = logging.getLogger()

    #sync_from_index  there are already indexes we will want to read them from file. \
        # (TODO: This can be used to check changes occured while script was not running (if )
    sync_from_index = True
    time_interval = int(sync_timer)
    #TODO: Add a keypress condition to stop the loop and make it run one last check before closing
    signal.signal(signal.SIGINT, signal_handler)
    while True:
        Orchestration(syncer_ori, syncer_repo, sync_from_index)
        sync_from_index = False
        time.sleep(time_interval)
    