# importing the required libraries
import gspread
from datetime import datetime, timedelta
from dateutil import parser
import threading
import json
import traceback
from ConcurrentList import ConcurrentList

class GSheetManager:
    # Hardcoded
    MAIN_GSHEET_NAME = 'Shift Automation'
    SHEET_NAME_CONFIGURATION = 'Configuration'

    # Ticket State sheet column headers to get respective values from Dictionary
    TICKET_ID_COL = 'Ticket'
    THREAD_ID_COL = 'Thread ID'
    MESSAGE_ID_COL = 'Message ID'
    MANAGER_ID_COL = 'Manager GChat ID'
    MANAGER_NAME_COL = 'Manager Name'
    
    # Configuration sheet column headers to get respective values from Dictionary
    CONFIGURATION_SPACEID_COL = 'SpaceId'
    CONFIGURATION_URLFORRESTREQUEST_COL = 'URLForRestRequest'
    CONFIGURATION_TICKETTIMEOUT_COL = 'TicketTimeout'
    CONFIGURATION_TIMEFORDATAFLUSH_COL = 'TimeForDataFlush'
    CONFIGURATION_TIMEFORMANAGERDATARELOAD_COL = 'TimeForManagerDataReload'
    CONFIGURATION_MANAGERDNDTIME_COL = 'ManagerDNDTime'
    CONFIGURATION_NUMBEROFITEMSBATCH_COL = 'NumberOfItemsInBatch'
    CONFIGURATION_SHIFT2STARTTIME_COL = 'Shift2StartTime'
    CONFIGURATION_SHIFT3STARTTIME_COL = 'Shift3StartTime'
    CONFIGURATION_SHIFT4STARTTIME_COL = 'Shift4StartTime'
    CONFIGURATION_SHEETNAME_MANAGERS_COL = 'ManagersSheetName'
    CONFIGURATION_SHEETNAME_STATEMANAGEMENT_COL = 'StateManagementSheetName'
    CONFIGURATION_SHEETNAME_TICKETSTATE_COL = 'TicketStateSheetName'
    CONFIGURATION_SHEETNAME_MANAGERSTATE_COL = 'ManagerStateSheetName'
    CONFIGURATION_SHEETNAME_TRACKER_COL = 'TrackerSheetName'
    
    # Configurable Parameters loaded from GSheet Configuration
    sheet_name_managers = 'Managers'
    sheet_name_statemanagement = 'StateManagement'
    sheet_name_ticketstate = 'TicketState'
    sheet_name_managerstate = 'ManagerState'
    sheet_name_tracker = 'Tracker'
    space_id = 'spaces/XXXXXXXXXXX'
    url_for_rest_request = ''
    ticket_timeout = 300
    time_for_tracker_data_flush = 10.0
    time_for_manager_data_reload = 7200.0
    manager_dnd_time = 3600.0
    number_of_items_in_batch = 49
    shift2_start_time = 6
    shift3_start_time = 12
    shift4_start_time = 18

    # Class variables
    sheet_configuration = None
    sheet_managers = None
    sheet_statemanagement = None
    sheet_ticketstatemanagement = None
    sheet_tracker = None
    sheet_managerstate = None
    list_of_tracker_data = None

    # Local cache of ticket states
    ticket_to_ticketState_map = {}

    # Local cache of all manager data
    list_of_managers = []

    # Manager Last Activity Timestamp tracker to help recognize managers in dnd
    manager_last_interaction_time_map = {}

    # Local cache of last row of manager for current shift and current shift
    last_manager_row_number_cached = 0
    current_shift_cached = 0
    logger = None

    def __init__(self, logger, credentials):
        # Required for keeping GSheet operations thread safe
        self.lock = threading.Lock()
        self.logger = logger

        # authorize the clientsheet 
        client = gspread.authorize(credentials)

        # get the instance of the Spreadsheet
        sheet = client.open(self.MAIN_GSHEET_NAME)

        # get the Configurations sheet and load configuration
        self.sheet_configuration = sheet.worksheet(self.SHEET_NAME_CONFIGURATION)
        self.load_configuration()

        self.list_of_tracker_data = ConcurrentList(self.number_of_items_in_batch)

        self.sheet_managers = sheet.worksheet(self.sheet_name_managers)

        self.sheet_statemanagement = sheet.worksheet(self.sheet_name_statemanagement)

        self.sheet_ticketstatemanagement = sheet.worksheet(self.sheet_name_ticketstate)

        self.sheet_managerstate = sheet.worksheet(self.sheet_name_managerstate)

        self.sheet_tracker = sheet.worksheet(self.sheet_name_tracker)

        self.initialize_maps()
        
        self.flush_data_to_tracker_on_timer()
        self.reload_manager_data_on_timer()

    def reload_configuration_during_runtime(self):
        """Some configurations can be changed during runtime without need of application restart"""
        with self.lock:
            self.load_configuration()

    def load_configuration(self):
        """Load all configuration from sheet to local values"""
        try:
            configurationMap = self.sheet_configuration.get_all_records()[0]
            self.sheet_name_managers = configurationMap[self.CONFIGURATION_SHEETNAME_MANAGERS_COL]
            self.sheet_name_statemanagement = configurationMap[self.CONFIGURATION_SHEETNAME_STATEMANAGEMENT_COL]
            self.sheet_name_ticketstate = configurationMap[self.CONFIGURATION_SHEETNAME_TICKETSTATE_COL]
            self.sheet_name_managerstate = configurationMap[self.CONFIGURATION_SHEETNAME_MANAGERSTATE_COL]
            self.sheet_name_tracker = configurationMap[self.CONFIGURATION_SHEETNAME_TRACKER_COL]
            self.space_id = configurationMap[self.CONFIGURATION_SPACEID_COL]
            self.url_for_rest_request = configurationMap[self.CONFIGURATION_URLFORRESTREQUEST_COL]
            self.ticket_timeout = configurationMap[self.CONFIGURATION_TICKETTIMEOUT_COL]
            self.time_for_tracker_data_flush = configurationMap[self.CONFIGURATION_TIMEFORDATAFLUSH_COL]
            self.time_for_manager_data_reload = configurationMap[self.CONFIGURATION_TIMEFORMANAGERDATARELOAD_COL]
            self.manager_dnd_time = configurationMap[self.CONFIGURATION_MANAGERDNDTIME_COL]
            self.number_of_items_in_batch = configurationMap[self.CONFIGURATION_NUMBEROFITEMSBATCH_COL]
            self.shift2_start_time = configurationMap[self.CONFIGURATION_SHIFT2STARTTIME_COL]
            self.shift3_start_time = configurationMap[self.CONFIGURATION_SHIFT3STARTTIME_COL]
            self.shift4_start_time = configurationMap[self.CONFIGURATION_SHIFT4STARTTIME_COL]
        except:
            self.logger.error("Error in load_configuration in GSheetManager: " + traceback.format_exc())

    def reload_manager_data_on_timer(self):
        """Manager data to be loaded from sheet on a timer in case of any change"""
        threading.Timer(self.time_for_manager_data_reload, self.reload_manager_data_on_timer).start()
        try:
            self.reload_manager_data_during_runtime()
        except:
            self.logger.error("Error in reload_manager_data_on_timer in GSheetManager: " + traceback.format_exc())

    def reload_manager_data_during_runtime(self):
        """Manager data from sheets can be loaded manually during runtime in case of any changes"""
        with self.lock:
            self.list_of_managers = self.sheet_managers.get_all_values()

    def reload_ticket_state_during_runtime(self):
        """Ticket state from sheets can be loaded manually during runtime in case of any changes"""
        with self.lock:
            dictionaryOfAllRecords = self.sheet_ticketstatemanagement.get_all_records()
            removedRecords = self.ticket_to_ticketState_map.copy()
            self.ticket_to_ticketState_map.clear()
            for record in dictionaryOfAllRecords:
                jiraId = record[self.TICKET_ID_COL]
                self.ticket_to_ticketState_map[jiraId] = record
                removedRecords.pop(jiraId, None)
            return removedRecords.values(), dictionaryOfAllRecords

    def initialize_maps(self):
        """Load all data into local lists and maps to reduce overhead of interacting with GSheets"""
        try:
            listOfManagerState = self.sheet_managerstate.get_all_values()
            for managerState in listOfManagerState[1:]:
                self.manager_last_interaction_time_map[managerState[0]] = parser.parse(managerState[1])
            self.list_of_managers = self.sheet_managers.get_all_values()
            dictionaryOfAllRecords = self.sheet_ticketstatemanagement.get_all_records()
            self.ticket_to_ticketState_map.clear()
            for record in dictionaryOfAllRecords:
                self.ticket_to_ticketState_map[record[self.TICKET_ID_COL]] = record
        except:
            self.logger.error("Error in initialize_maps in GSheetManager: " + traceback.format_exc())

    def get_ticket_states_map(self):
        """Get a copy of the ticket state dictionary"""
        with self.lock:
            return self.ticket_to_ticketState_map.copy()

    def get_manager_id(self):
        """Get next Manager Id. 
        It checks Dnd for manager as well and loops through managers till one is not in Dnd.
        If not found, dndtimeout of the first manager is returned, else 0 is returned.
        It returns the selected manager Id and dnd timeout if any."""
        with self.lock:
            currentShift = self.get_shift()
            shiftColumnNumber = currentShift + 1
            managersRowCount = len(self.list_of_managers)
            
            if self.last_manager_row_number_cached == 0 or self.current_shift_cached != currentShift:
                self.current_shift_cached = currentShift
                self.last_manager_row_number_cached = int(self.sheet_statemanagement.cell(col=shiftColumnNumber,row=4).value)   

            lastRowNumberFromState = self.last_manager_row_number_cached + 1
            if (lastRowNumberFromState > managersRowCount):
                lastRowNumberFromState = 2

            firstSelectedManagerId = 0
            selectedManagerId = 0
            dndTimeoutForManager = 1
            while (dndTimeoutForManager != 0):
                firstValueOflLstRowNumberFromState = 0
                while (int(self.list_of_managers[lastRowNumberFromState-1][4]) != currentShift):
                    if firstValueOflLstRowNumberFromState == 0:
                        firstValueOflLstRowNumberFromState = lastRowNumberFromState
                    elif firstValueOflLstRowNumberFromState == lastRowNumberFromState:
                        return 0, self.manager_dnd_time
                    lastRowNumberFromState+=1
                    if (lastRowNumberFromState > managersRowCount):
                        lastRowNumberFromState = 2
                selectedManagerId = self.list_of_managers[lastRowNumberFromState-1][5]
                newDndTimeoutForManager = self.has_activity_in_last_hour(selectedManagerId)
                if dndTimeoutForManager == 1 or newDndTimeoutForManager < dndTimeoutForManager:
                    dndTimeoutForManager = newDndTimeoutForManager
                if dndTimeoutForManager == 0:
                    ticketTimeoutTimeWithBuffer = self.manager_dnd_time - self.ticket_timeout - 30
                    self.manager_last_interaction_time_map[selectedManagerId] = datetime.utcnow() - timedelta(seconds=ticketTimeoutTimeWithBuffer)
                    break
                elif firstSelectedManagerId == 0:
                    firstSelectedManagerId = selectedManagerId
                elif firstSelectedManagerId == selectedManagerId:
                    break
            
            self.last_manager_row_number_cached = lastRowNumberFromState
            self.sheet_statemanagement.update_cell(4, shiftColumnNumber, lastRowNumberFromState)
            return selectedManagerId, dndTimeoutForManager

    def get_shift(self):
        """Returns current shift as per UTC time. The shift start times are configured in GSheet"""
        currentHour = datetime.utcnow().hour
        
        if (currentHour >= self.shift4_start_time):
            return 4
        elif (currentHour >= self.shift3_start_time):
            return 3
        elif (currentHour >= self.shift2_start_time):
            return 2
        else:
            return 1
    
    def append_ticket_status(self, jiraId, managerId, managerName, threadId, messageId):
        """Only should be called for new ticket, appends the new status to local map as well as GSheet"""
        with self.lock:
            self.ticket_to_ticketState_map[jiraId] = {}
            self.ticket_to_ticketState_map[jiraId][self.TICKET_ID_COL] = jiraId
            self.ticket_to_ticketState_map[jiraId][self.THREAD_ID_COL] = threadId
            self.ticket_to_ticketState_map[jiraId][self.MANAGER_ID_COL] = managerId
            self.ticket_to_ticketState_map[jiraId][self.MANAGER_NAME_COL] = managerName
            self.ticket_to_ticketState_map[jiraId][self.MESSAGE_ID_COL] = messageId
            self.sheet_ticketstatemanagement.append_row([jiraId, managerName, managerId, messageId, threadId])
    
    def update_ticket_status(self, jiraId, managerId, managerName, messageId):
        """Only for already existing ticket, updates the status to local map as well as GSheet"""
        with self.lock:
            cell = self.get_cell(self.sheet_ticketstatemanagement, jiraId)
            if (cell is not None):
                self.ticket_to_ticketState_map[jiraId][self.MANAGER_ID_COL] = managerId
                self.ticket_to_ticketState_map[jiraId][self.MANAGER_NAME_COL] = managerName
                self.ticket_to_ticketState_map[jiraId][self.MESSAGE_ID_COL] = messageId
                cell_list = self.sheet_ticketstatemanagement.range(f'B{cell.row}:D{cell.row}')
                cell_values = [managerName, managerId, messageId]
                for i, val in enumerate(cell_values):
                    cell_list[i].value = val
                self.sheet_ticketstatemanagement.update_cells(cell_list)
            # else: # Anomaly, should not happen
            #     append_ticket_status(jiraId, managerId, managerName, messageId, threadId)
        

    def get_ticket_status(self, jiraId):
        """Gets ticket status if present"""
        with self.lock:
            if (jiraId in self.ticket_to_ticketState_map):
                return self.ticket_to_ticketState_map[jiraId]
            return None

    def remove_ticket_status(self, jiraId):
        """Removes existing ticket status, only called on acceptance of a ticket"""
        with self.lock:
            self.ticket_to_ticketState_map.pop(jiraId, None)
            cell = self.get_cell(self.sheet_ticketstatemanagement, jiraId)
            if (cell is not None):
                self.sheet_ticketstatemanagement.delete_row(cell.row)

    def add_data_to_tracker(self, timestamp, jiraId, managerName, status):
        """Adds data to tracker list to be updated later in GSheet on timer"""
        self.list_of_tracker_data.add([str(timestamp), jiraId, managerName, status])

    def flush_data_to_tracker_on_timer(self):
        """Batch update GSheet with Tracker data"""
        threading.Timer(self.time_for_tracker_data_flush, self.flush_data_to_tracker_on_timer).start()
        try:
            dataToFlush = self.list_of_tracker_data.getAll()
            if len(dataToFlush) > 0:
                self.sheet_tracker.append_rows(dataToFlush)
        except:
            self.logger.error("Error in flush_data_to_tracker_on_timer: " + traceback.format_exc())

    def record_manager_last_activity(self, timestamp, managerId):
        """Record the last timestamp of a manager activity (decline or acceptance), so as to add manager to dnd"""
        with self.lock:
            self.manager_last_interaction_time_map[managerId] = timestamp
        cell = self.get_cell(self.sheet_managerstate, managerId)
        if cell is not None:
            self.sheet_managerstate.update_cell(cell.row, cell.col + 1, str(timestamp))
        else:
            self.sheet_managerstate.append_row([managerId, str(timestamp)])

    def has_activity_in_last_hour(self, managerId):
        """Check if a manager is in dnd"""
        if managerId in self.manager_last_interaction_time_map:
            timeSinceLastActivity = (datetime.utcnow() - self.manager_last_interaction_time_map.get(managerId)).total_seconds()
            if (timeSinceLastActivity <= self.manager_dnd_time - 5):
                return self.manager_dnd_time - timeSinceLastActivity
        return 0

    def get_cell(self, sheet, dataToFind):
        """get_cell in gspread api throws exception if data is not found. Returns None in case of that"""
        try:
            cell = sheet.find(dataToFind)
            return cell
        except:  # gspread.exceptions.CellNotFound
            return None
