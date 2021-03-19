from flask import Flask, request, json, make_response
from threading import Thread
import google.auth
from googleapiclient.discovery import build 
from oauth2client.service_account import ServiceAccountCredentials
from GSheetManager import GSheetManager
import traceback
from datetime import datetime
from TimeoutHandler import TimeoutHandler, RESPONSEDATA_ISINTERNALRESTREQUEST, RESPONSEDATA_ISMANAGERTIMEOUT
from RestRequestHandler import RestRequestHandler
import logging

# Message types supported in application currently.
EVENTTYPE_MESSAGE = 'MESSAGE'
EVENTTYPE_DELETE = 'DELETE'
EVENTTYPE_CARDCLICKED = 'CARD_CLICKED'
EVENTTYPE_RELOADMANAGERDATA = 'RELOAD_MANAGER_DATA'
EVENTTYPE_RELOADTICKETSTATE = 'RELOAD_TICKET_STATE'
EVENTTYPE_RELOADCONFIG = 'RELOAD_CONFIG'

# Data received in requests.
RESPONSEDATA_JIRAID = 'jiraId'
RESPONSEDATA_TYPE = 'type'
RESPONSEDATA_TEXT = 'text'
RESPONSEDATA_USER = 'user'
RESPONSEDATA_NAME = 'name'
RESPONSEDATA_THREAD = 'thread'
RESPONSEDATA_MESSAGENAME = 'messageName'
RESPONSEDATA_MESSAGE = 'message'
RESPONSEDATA_ACTION = 'action'
RESPONSEDATA_ACTIONMETHODNAME = 'actionMethodName'
RESPONSEDATA_PARAMETERS = 'parameters'
RESPONSEDATA_VALUE = 'value'

# Possible action methods in case of a card click event.
ACTIONMETHOD_ACCEPT = "accept"
ACTIONMETHOD_DECLINE = "decline"
ACTIONMETHOD_DONE = "done"

# Ticket status for the tracker.
TICKET_STATUS_PINGED = 'Pinged'
TICKET_STATUS_ACCEPTED = 'Accepted'
TICKET_STATUS_DECLINED = 'Declined'
TICKET_STATUS_TIMEDOUT = 'TimedOut'
TICKET_STATUS_COMPELTED = 'Completed'

scopes = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/chat.bot']
creds = ServiceAccountCredentials.from_json_keyfile_name('rcabot.json', scopes)
application = app = Flask(__name__)
logger = logging.getLogger(__name__)
restRequestHandler = RestRequestHandler(creds)
gSheetManager = GSheetManager(logger, creds)
timeoutHandler = TimeoutHandler(logger, gSheetManager.ticket_timeout, gSheetManager.url_for_rest_request, gSheetManager.get_ticket_states_map(), gSheetManager.TICKET_ID_COL, gSheetManager.MANAGER_ID_COL)

@app.route('/', methods=['POST', 'GET'])
def on_event():
    """All requests land here. GET is only implemented for Heartbeat."""
    try:
        if request.method == 'GET':
            return get_success_response()
        event = request.get_json()
        if event is None or RESPONSEDATA_TYPE not in event:
            return get_success_response()
        eventType = event[RESPONSEDATA_TYPE].strip().upper()
        if (eventType == EVENTTYPE_MESSAGE):
            return on_send_new_message(event)
        elif(eventType == EVENTTYPE_CARDCLICKED):
            return on_card_click_request(event)
        elif(eventType == EVENTTYPE_RELOADMANAGERDATA):
            return on_reload_manager_data_request()
        elif(eventType == EVENTTYPE_RELOADTICKETSTATE):
            return on_reload_ticket_state_request()
        elif(eventType == EVENTTYPE_RELOADCONFIG):
            return on_reload_config_request()

        logger.warning("Unknown request type received: " + eventType)
        return json.dumps({ "status": "Unknown request Type: " + eventType }), 500
    except:
        errorFormat = "Unexpected error in rest request: " + traceback.format_exc()
        logger.error(errorFormat)
        return json.dumps({ "status": errorFormat }), 500

def on_reload_manager_data_request():
    """Request to reload manager data during runtime."""
    gSheetManager.reload_manager_data_during_runtime()
    return get_success_response()

def on_reload_ticket_state_request():
    """Request to reload ticket states during runtime.
        This is implemented only for unforeseen circumstances and should be avoided."""
    removedRecordsList, allNewRecordsList = gSheetManager.reload_ticket_state_during_runtime()
    timeoutHandler.update_ticket_states_during_runtime(removedRecordsList, allNewRecordsList)
    return get_success_response()

def on_reload_config_request():
    """Request to reload configuration during runtime."""
    gSheetManager.reload_configuration_during_runtime()
    timeoutHandler.update_properties(gSheetManager.ticket_timeout, gSheetManager.url_for_rest_request)
    return get_success_response()

def on_send_new_message(event):
    """Request to send a message for a ticket. It could be in case of New, Timeout and Decline."""
    if RESPONSEDATA_JIRAID not in event:
        return {}, 500
    
    jiraId = event[RESPONSEDATA_JIRAID].strip()
    ticketStatus = gSheetManager.get_ticket_status(jiraId)
    if ticketStatus is not None and RESPONSEDATA_ISINTERNALRESTREQUEST not in event:
        return json.dumps({ "status": f"Request for {jiraId} already received" }), 500
    
    managerId,dndTimeoutForManager = gSheetManager.get_manager_id()
    bot_message = get_new_bot_message(jiraId, managerId)

    if ticketStatus:
        isManagerTimeout = RESPONSEDATA_ISMANAGERTIMEOUT in event
        if isManagerTimeout:
            oldManagerName = ticketStatus[gSheetManager.MANAGER_NAME_COL]
            message_updated = { "text": f"{jiraId} has timed out for {oldManagerName}" }
            restRequestHandler.send_rest_request_chat(restRequestHandler.REQUEST_URL_UPDATE.format(ticketStatus[gSheetManager.MESSAGE_ID_COL], restRequestHandler.REQUEST_UPDATEMASK), restRequestHandler.REQUESTTYPE_PUT, message_updated)
            gSheetManager.add_data_to_tracker(datetime.utcnow(), jiraId, oldManagerName, TICKET_STATUS_TIMEDOUT)
        if dndTimeoutForManager > 0:
            response = make_response(json.dumps({ "status": "Success", "managerId": 0, "newTimeOut": dndTimeoutForManager }))
            response.headers['content-type'] = 'application/json'
            return response
        else:
            responseOnMessageCreation = restRequestHandler.send_rest_request_chat(restRequestHandler.REQUEST_URL_CREATE_IN_THREAD.format(gSheetManager.space_id, ticketStatus[gSheetManager.THREAD_ID_COL]), restRequestHandler.REQUESTTYPE_POST, bot_message)
            managerName = responseOnMessageCreation[RESPONSEDATA_TEXT][1:]
            gSheetManager.update_ticket_status(jiraId, managerId, managerName, responseOnMessageCreation[RESPONSEDATA_NAME])
            gSheetManager.add_data_to_tracker(datetime.utcnow(), jiraId, managerName, TICKET_STATUS_PINGED)
    else:
        if dndTimeoutForManager > 0:
            timeoutHandler.add_thread(jiraId, 0, dndTimeoutForManager)
        else:
            responseOnMessageCreation = restRequestHandler.send_rest_request_chat(restRequestHandler.REQUEST_URL_CREATE.format(gSheetManager.space_id), restRequestHandler.REQUESTTYPE_POST, bot_message)
            timeoutHandler.add_thread(jiraId, managerId)
            managerName = responseOnMessageCreation[RESPONSEDATA_TEXT][1:]
            gSheetManager.append_ticket_status(jiraId, managerId, managerName, responseOnMessageCreation[RESPONSEDATA_THREAD][RESPONSEDATA_NAME], responseOnMessageCreation[RESPONSEDATA_NAME])
            gSheetManager.add_data_to_tracker(datetime.utcnow(), jiraId, managerName, TICKET_STATUS_PINGED)

    response = make_response(json.dumps({ "status": "Success", "managerId": managerId }))
    response.headers['content-type'] = 'application/json'
    return response

def on_card_click_request(event):
    """Request on any of the card buttons clicked."""
    managerName = event[RESPONSEDATA_MESSAGE][RESPONSEDATA_TEXT][1:]
    eventAction = event[RESPONSEDATA_ACTION]
    actionMethodName = eventAction[RESPONSEDATA_ACTIONMETHODNAME]
    parameters = eventAction[RESPONSEDATA_PARAMETERS]
    jiraId = parameters[0][RESPONSEDATA_VALUE]
    managerId = parameters[1][RESPONSEDATA_VALUE]
    gChatIdOfClickEvent = event[RESPONSEDATA_USER][RESPONSEDATA_NAME].split("/")[1]
    
    # If button click event is not sent by mentioned user
    if (gChatIdOfClickEvent != managerId):
        return {}, 500
    
    timestamp = datetime.utcnow()
    if (actionMethodName == ACTIONMETHOD_ACCEPT):
        timeoutHandler.remove_thread_on_response(jiraId, managerId, False)
        gSheetManager.remove_ticket_status(jiraId)
        gSheetManager.add_data_to_tracker(timestamp, jiraId, managerName, TICKET_STATUS_ACCEPTED)
        gSheetManager.record_manager_last_activity(timestamp, managerId)
        return get_accept_bot_message(jiraId, managerId, managerName)
    elif (actionMethodName == ACTIONMETHOD_DECLINE):
        gSheetManager.record_manager_last_activity(timestamp, managerId)
        timeoutHandler.remove_thread_on_response(jiraId, managerId, True)
        gSheetManager.add_data_to_tracker(timestamp, jiraId, managerName, TICKET_STATUS_DECLINED)
        return get_declined_bot_message(jiraId, managerName)
    else:
        gSheetManager.add_data_to_tracker(datetime.utcnow(), jiraId, managerName, TICKET_STATUS_COMPELTED)
        return get_done_bot_message(jiraId, managerName)


def get_new_bot_message(jiraId, managerId):
    return {
        "cards": [
            {
            "header": {
                "title": "New RCA Notfication"
            },
            "sections": [
                {
                "widgets": [
                    {
                    "buttons": [
                        {
                        "textButton": {
                            "text": jiraId,
                            "onClick": {
                            "openLink": {
                                "url": f"https://jira.devfactory.com/browse/{jiraId}"
                            }
                            }
                        }
                        }
                    ]
                    }
                ]
                },
                {
                    "widgets": [
                    {
                        "buttons": [
                        {
                            "textButton": {
                            "text": "Accept",
                            "onClick": {
                                "action": {
                                "actionMethodName": ACTIONMETHOD_ACCEPT,
                                "parameters": [
                                    {
                                    "key": "jiraId",
                                    "value": jiraId
                                    },
                                    {
                                    "key": "managerId",
                                    "value": managerId
                                    }
                                ]
                                }
                            }
                            }
                        },
                        {
                            "textButton": {
                            "text": "Decline",
                            "onClick": {
                                "action": {
                                "actionMethodName": ACTIONMETHOD_DECLINE,
                                "parameters": [
                                    {
                                    "key": "jiraId",
                                    "value": jiraId
                                    },
                                    {
                                    "key": "managerId",
                                    "value": managerId
                                    }
                                ]
                                }
                            }
                            }
                        }
                        ]
                    }
                ]
                }
            ]
            }
        ],
        "text": f"<users/{managerId}>"
    }

def get_accept_bot_message(jiraId, managerId, managerName):
    return {
        "actionResponse":{
            "type":"UPDATE_MESSAGE"
        },
        "cards": [
            {
            "header": {
                "title": f"Assigned to {managerName}"
            },
            "sections": [
                {
                "widgets": [
                    {
                        "textParagraph": {
                            "text": "Please work on"
                        },
                        "buttons": [
                            {
                            "textButton": {
                                "text": jiraId,
                                "onClick": {
                                    "openLink": {
                                        "url": f"https://jira.devfactory.com/browse/{jiraId}"
                                    }
                                }
                            }
                            }
                        ]
                    }
                ]
                },
                {
                    "widgets": [
                    {
                        "buttons": [
                        {
                            "textButton": {
                            "text": "Done",
                            "onClick": {
                                "action": {
                                "actionMethodName": ACTIONMETHOD_DONE,
                                "parameters": [
                                    {
                                    "key": "jiraId",
                                    "value": jiraId
                                    },
                                    {
                                    "key": "managerId",
                                    "value": managerId
                                    }
                                ]
                                }
                            }
                            }
                        }
                        ]
                    }
                ]
                }
            ]
            }
        ],
        "text": f"<users/{managerId}>"
    }

def get_declined_bot_message(jiraId, managerName):
    return {
        "actionResponse":{
            "type":"UPDATE_MESSAGE"
        },
        "cards": [],
        "text": f"{jiraId} was declined by {managerName}"
    }

def get_done_bot_message(jiraId, managerName):
    return {
        "actionResponse":{
            "type":"UPDATE_MESSAGE"
        },
        "cards": [],
        "text": f"{jiraId} was completed by {managerName}"
    }

def get_success_response():
    return json.dumps({ "status": "Success" }), 200

if __name__ == '__main__':
    app.run()