from win32gui import GetWindowText, GetForegroundWindow 
import time
while True:
    time.sleep(3)
    print(GetWindowText(GetForegroundWindow()))
