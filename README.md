# <img src='./logo.svg' card_color="#FF8600" width="50" style="vertical-align:bottom" style="vertical-align:bottom">Alerts  
  
## Summary  
  
A skill to schedule alarms, timers, and reminders


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

## Contact Support
Use [this link](https://neongecko.com/ContactUs) or
[submit an issue on GitHub](https://help.github.com/en/articles/creating-an-issue)

## Incompatible Skills
This skill has known intent collisions with the following skills:
- [skill-reminder.mycroftAI](https://github.com/mycroftai/skill-reminder)
- [skill-alarm.mycroftAI](https://github.com/mycroftai/skill-alarm)
- [mycroft-timer.mycroftAI](https://github.com/mycroftai/mycroft-timer)

## Credits
[NeonGeckoCom](https://github.com/NeonGeckoCom)
[NeonDaniel](https://github.com/NeonDaniel)

## Category
**Productivity**
Daily

## Tags
#NeonGecko Original
#NeonAI
#alert
#alarm
#timer
#reminder
#schedule
