from TimerEventObjData import TimerEventObjData
import threading
import httplib2
import json
import traceback

EVENTTYPE_MESSAGE = "MESSAGE"
RESPONSEDATA_ISMANAGERTIMEOUT = "isManagerTimeout"
RESPONSEDATA_ISINTERNALRESTREQUEST = "isInternalRestRequest"
RESPONSEDATA_TRUE = "True"

class TimeoutHandler():
    ticket_id_col = 'Ticket'
    manager_id_col = 'Manager GChat ID'
    tickets_on_timer = {}
    timeout_for_ticket = 300.0
    url_for_rest_request = ''
    logger = None

    def __init__(self, logger, timeout, urlForRestRequest, list_of_cached_ticket_states, ticket_id_col, manager_id_col):
        self.lock = threading.Lock()
        self.logger = logger
        self.tickets_on_timer = {}
        self.timeout_for_ticket = timeout
        self.url_for_rest_request = urlForRestRequest
        self.ticket_id_col = ticket_id_col
        self.manager_id_col = manager_id_col

        self.add_cached_tickets_to_thread(list_of_cached_ticket_states)
    
    def add_cached_tickets_to_thread(self, list_of_cached_ticket_states):
        """When loading ticket states from GSheet during initialization, the timeout threads of the tickets are added."""
        try:
            if len(list_of_cached_ticket_states) > 0:
                for key, value in list_of_cached_ticket_states.items():
                    self.add_thread(value[self.ticket_id_col], value[self.manager_id_col], self.timeout_for_ticket)
        except:
            self.logger.error("Error in add_cached_tickets_to_thread in TimeoutHandler: " + traceback.format_exc())

    def update_ticket_states_during_runtime(self, removedRecordsList, allNewRecordsList):
        """When loading ticket states from GSheet during runtime, the timeout threads of the tickets are removed/added.
        This is implemented only for unforeseen circumstances and should be avoided."""
        with self.lock:
            for record in removedRecordsList:
                timerEventObjData = self.tickets_on_timer.pop(record[self.ticket_id_col], None)
                if timerEventObjData is not None:
                    timerEventObjData.isDeclined = False
                    timerEventObjData.eventObject.set()
        for record in allNewRecordsList:
            self.add_thread(record[self.ticket_id_col], record[self.manager_id_col], self.timeout_for_ticket)

    def update_properties(self, timeout, urlForRestRequest):
        """When loading configuration from GSheet during runtime, update the timeout properties as well."""
        with self.lock:
            self.timeout_for_ticket = timeout
            self.url_for_rest_request = urlForRestRequest

    def add_thread(self, jiraId, managerId, timeout=0):
        """Create a timeout thread for ticket."""
        with self.lock:
            if jiraId not in self.tickets_on_timer:
                if timeout == 0:
                    timeout = self.timeout_for_ticket
                eventObject = threading.Event()
                timerEventObjData = TimerEventObjData(jiraId, managerId, eventObject)
                threadObject = threading.Thread(target=self.send_rest_request, args=(timerEventObjData, timeout, ))
                threadObject.name = jiraId
                self.tickets_on_timer[jiraId] = timerEventObjData
                threadObject.start()

    def remove_thread_on_response(self, jiraId, managerId, isDeclined):
        """Interrupt a timeout thread for ticket. Remove thread completely in case it is accepted."""
        with self.lock:
            timerEventObjData = self.tickets_on_timer.get(jiraId)
            if timerEventObjData is not None and timerEventObjData.managerId == int(managerId):
                if not timerEventObjData.eventObject.is_set():
                    timerEventObjData.isDeclined = isDeclined
                    timerEventObjData.eventObject.set()
                    if not isDeclined:
                        timerEventObjData = self.tickets_on_timer.pop(jiraId, None)

    def send_rest_request(self, timerEventObjData, timeoutForTicket):
        """Timeout thread of the ticket used to send rest requests whenever ticket times out."""
        while (True):
            timerEventObjData.eventObject.clear()
            timerEventObjData.eventObject.wait(timeout=timeoutForTicket) 
            if timerEventObjData.eventObject.is_set() and timerEventObjData.isDeclined == False:
                break
            try:
                timeoutForTicket = self.timeout_for_ticket
                isManagerTimeout = timerEventObjData.managerId != 0 and not timerEventObjData.isDeclined
                timerEventObjData.isDeclined = False
                http = httplib2.Http()
                if isManagerTimeout:
                    body =  {
                                "type":EVENTTYPE_MESSAGE,
                                "jiraId":timerEventObjData.jiraId,
                                RESPONSEDATA_ISINTERNALRESTREQUEST: RESPONSEDATA_TRUE,
                                RESPONSEDATA_ISMANAGERTIMEOUT:isManagerTimeout
                            }
                else:
                    body =  {
                                "type":EVENTTYPE_MESSAGE,
                                "jiraId":timerEventObjData.jiraId,
                                RESPONSEDATA_ISINTERNALRESTREQUEST: RESPONSEDATA_TRUE
                            }

                response, content = http.request(self.url_for_rest_request, 
                                    method="POST", 
                                    headers={'Content-type': 'application/json'},
                                    body=json.dumps(body))
                
                if response.status  == 200:
                    responseData = json.loads(content)
                    timerEventObjData.managerId = int(responseData['managerId'])
                    if timerEventObjData.managerId == 0:
                        # When all managers are busy/dnd, managerId is 0 in response
                        timeoutForTicket = int(responseData['newTimeOut'])
                else:
                    self.logger.warning(f"Invalid response received in timeout for {timerEventObjData.jiraId}: {response}")
            except:
                self.logger.error(f"Error in timeout for {timerEventObjData.jiraId}: {traceback.format_exc()}")