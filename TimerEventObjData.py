class TimerEventObjData():
    jiraId = ''
    managerId = 0
    eventObject = None
    isDeclined = False

    def __init__(self, jiraId, managerId, eventObject):
        self.jiraId = jiraId
        self.managerId = int(managerId)
        self.eventObject = eventObject
        self.isDeclined = False