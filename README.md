
# <img src='https://0000.us/klatchat/app/files/neon_images/icons/neon_skill.png' card_color="#FF8600" width="50" style="vertical-align:bottom">Alerts  
  
## Summary  
  
A skill to schedule alarms, timers, and reminders
  
## Requirements  
All of the requirements should be installed automatically during original Neon’s setup. If you have any problems, or are
adding the skill later on, please [feel free to contact our team for support](#contact-support).

  
## Description  
  
The skill provides functionality to create alarms, timers and reminders, remove them by name, time, or type, and ask for
what is active. You may also silence all alerts and ask for a summary of what was missed if you were away, your device
was off, or you had quiet hours enabled.

Alarms and reminders may be set to recur daily or weekly. An active alert may be snoozed for a specified amount of time
while it is active. Any alerts that are not acknowledged will be added to a list of missed alerts that may be read and
cleared when requested.
    
  
## Examples  
  
If you are skipping wake words, say `Neon` followed by any of the following, otherwise say your `Wake Word`:

- "set an alarm for 8 am"
- "when is my next alarm"
- "cancel my 8 am alarm"

- "set a 5 minute timer"
- "how much time is left"

- "remind me to go home at 6"
- "remind me to take out the trash every thursday at 7 pm"
- "what are my reminders"

- "cancel all (alarms/timers/reminders)"

- "go to sleep"
- "quiet hours"

If there is an active alert (expired and currently speaking or playing), you may snooze or dismiss it:

- "stop"

- "snooze"
- "snooze for 1 minute"
  
If you had quiet hours enabled, your device was off, or you were away and missed an alert, you may ask for a summary:

- "wake up"
- "what did i miss"
- "did i miss anything"


## Location  
  

     ${skills}/alerts.neon

## Files
<details>
<summary>Click to expand.</summary>
<br>

        alerts.neon/__pycache__
        alerts.neon/__pycache__/__init__.cpython-36.pyc
        alerts.neon/AlertSkill.yml
        alerts.neon/vocab
        alerts.neon/vocab/en-us
        alerts.neon/vocab/en-us/alarm.voc
        alerts.neon/vocab/en-us/cancel.voc
        alerts.neon/vocab/en-us/next.voc
        alerts.neon/vocab/en-us/endQuietHours.voc
        alerts.neon/vocab/en-us/timer.voc
        alerts.neon/vocab/en-us/list.voc
        alerts.neon/vocab/en-us/reminder.voc
        alerts.neon/vocab/en-us/snooze.voc
        alerts.neon/vocab/en-us/set.voc
        alerts.neon/vocab/en-us/all.voc
        alerts.neon/vocab/en-us/Neon.voc
        alerts.neon/vocab/en-us/startQuietHours.voc
        alerts.neon/vocab/en-us/howMuchTime.voc
        alerts.neon/README.md
        alerts.neon/regex
        alerts.neon/regex/en-us
        alerts.neon/regex/en-us/Time.rx
        alerts.neon/__init__.py
        alerts.neon/dialog
        alerts.neon/dialog/en-us
        alerts.neon/dialog/en-us/ConfirmSet.dialog
        alerts.neon/dialog/en-us/CancelAlert.dialog
        alerts.neon/dialog/en-us/ListAlerts.dialog
        alerts.neon/dialog/en-us/NextEvent.dialog
        alerts.neon/dialog/en-us/ConfirmTimer.dialog
        alerts.neon/dialog/en-us/CreateAtTime.dialog
        alerts.neon/dialog/en-us/UpcomingType.dialog
        alerts.neon/dialog/en-us/MissedAlert.dialog
        alerts.neon/dialog/en-us/AlertExpired.dialog
        alerts.neon/dialog/en-us/SnoozeAlert.dialog
        alerts.neon/dialog/en-us/ConfirmRecurring.dialog
        alerts.neon/dialog/en-us/NextAlert.dialog
        alerts.neon/dialog/en-us/CancelAll.dialog
        alerts.neon/dialog/en-us/WhatTime.dialog
        alerts.neon/dialog/en-us/TimerStatus.dialog
        alerts.neon/dialog/en-us/HowLong.dialog

</details>


## Class Diagram

  

## Available Intents
<details>
<summary>Show list</summary>
<br>


### alarm.voc

    alarm
    alarms
    wake me up

  

### all.voc

    all
    every

### cancel.voc

    cancel
    clear

### endQuietHours.voc

    wake up
    miss anything
    missed anything
    what did i miss

### howMuchTime.voc

    how much time is left
    timer status
    how long

### list.voc

    list my
    list all my
    list all of my
    tell me my
    tell me all my
    tell me all of my
    what are my

### Neon.voc

    neon
    leon
    nyan

### next.voc

    next
    
### reminder.voc

    reminder
    reminders
    remind me
    
### set.voc

    set
    create
    add
    make
    start
    
### snooze.voc

    snooze
    wait
    hold

### startQuietHours.voc

    go to sleep
    quiet hours
    
### timer.voc

    timer
    timers
    
</details>


## Details

### Text

	    Neon what are my reminders?
        >> You have the following reminders:
        >> to go home, Today at six p.m.
        
        Neon remind me to take out the trash every thursday at 7 pm.                                                                                             
        >> Your reminder is set for 7:00 pm, every thursday
                
        Neon enable quiet hours.                                                                                    
        >> Enabling quiet hours. I will not notify you of any alerts until you disable quiet hours.
        
        Neon what did I miss?
        >> You haven't missed any alerts.


### Picture

### Video

## Troubleshooting
There is a [known issue](https://github.com/ytdl-org/youtube-dl/issues/154) for youtube_dl, where the playback for certain videos and audio files will be temporarily unavailable if you request to listen to the same song and/or video multiple times in a row over a few days. The solution is to avoid requesting the same playback over and over again, try to word your request differently, or wait some time for the limitations to wear off.

Additionally, youtube_dl is currently under active development. Make sure to stay up-to-date by running Neon's update script or use the [manual requirements instructions](#requirements) to do it yourself.

## Contact Support
Use [this link](https://neongecko.com/ContactUs) or
[submit an issue on GitHub](https://help.github.com/en/articles/creating-an-issue)

## Credits
reginaneon djmcknight358 [neongeckocom](https://neongecko.com/)
