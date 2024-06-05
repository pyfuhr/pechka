import serial
import os

if os.name == 'nt':  # sys.platform == 'win32':
    from serial.tools.list_ports_windows import comports
elif os.name == 'posix':
    from serial.tools.list_ports_posix import comports

print(comports()[0].name)

exit()

with serial.Serial() as ser:
    try:
        ser.baudrate = 115200
        ser.port = 'COM3'
        ser.open()
        while 1:
            print(ser.readline().decode().rstrip())
            ser.flushInput()
    except KeyboardInterrupt:
        print("ctrl+c")
        ser.close()
        
