# RCA Bot

RCA Bot is a Google Chat Bot that notifies Managers when a Do Defect RCA ticket is ready for review.
* It goes through the manager's shift timings, selects a manager as per their availability and pings them.
* If a manager **Accepts** a ticket, it is removed from the cycle and no one else is pinged for it.
* If a manager **Declines** a ticket, another manager is looked for and pinged. The manager that declined the ticket goes into **DND** for a certain period of time (that can be configured). Said manager is not pinged again in that time frame.
* The ticket is available to pinged manager for a certain amount of time (that can be configured), the ticket times out for that manager and next available manager is pinged.
* This goes on till the ticket is accepted by a manager.
* There might be cases in which even though the last ticket state is declined or timed out, the ticket has not been pinged to any new manager. This can happen in case no manager is available in that shift or all available managers are in **DND**


## Deployment In Production
Elastic Beanstalk has been used to deploy the application in AWS. Simply go to the application on AWS console and uploading a zipped file containing the code.


## Local Deployment for Testing
The scripts are all Python and the Flask application can be run locally. But to access GChat to send actual messages, it requires a bot project to be created in the Google Cloud Platform. The bot in production **SHOULD NOT** be used for Testing.
Following steps need to be taken to run the application locally :-
* Create a bot project in Google Cloud Platform.
* Enable Google Chat API, Google Drive API and Google Sheets API in it.
* Add/Register a service account. Download JSON key for that account put its contents in the "rcabot.json" file in the project folder. **DO NOT** use the json file already there in the project. It is for production.
* Go to Google Chat API configuration in the project and configure Bot URL to point to where you are running this application. You can use ngrok if you are using local machine.
* Create a room in Google chat and add your created bot to it.
* Duplicate the Shift Automation GSheet **THE ONE IN PROD SHOULD NOT USED**. Share duplicated sheet with created service account. Put your GChat ID in Managers tab. Configure your application in Configuration sheet with required parameters (parameters explained below).
* Run your flask application and send rest request to it to initiate the process.


## Parameters
The configuration parameters can be found in the Configuration Sheet. They are described below :-
- SpaceId : The space Id of the room in which the bot should send the messages. It can be found by copying any thread link in the room.
- TicketTimeout : In how many seconds should the ticket time out for a manager.
- TimeForDataFlush : Tracker data is flushed in batches on a timer to the sheets. This configuration determines in how many seconds should each batch be flushed.
- NumberOfItemsInBatch : Number of items in a Tracker data batch.
- TimeForManagerDataReload : Manager data is reloaded on a timer to keep upto date with any changes in the sheet. This determines the number of seconds in which it should happen.
- ManagerDNDTime : Number of seconds a manager should remain in DND after accepting or declining a ticket.
- URLForRestRequest : URL on which the bot is running.
- Shift2StartTime : Start Time of Shift 2.
- Shift3StartTime : Start Time of Shift 3.
- Shift4StartTime : Start Time of Shift 4.
- ManagersSheetName : Sheet name of sheet containing all the Managers data.
- StateManagementSheetName : Sheet name of sheet used for managing shift state of application (which manager it last pinged in current shift).
- TicketStateSheetName : Sheet name of sheet used for managing ticket states which are currently in the cycle.
- TrackerSheetName : Sheet name of sheet containing all the tracker data.
- ManagerStateSheetName : Sheet name of sheet used for managing Manager state data (for DND).