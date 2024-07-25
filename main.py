from PyQt5 import QtWidgets, uic, QtCore
from pyqtgraph import PlotWidget
import pyqtgraph
import sys
import serial
from time import sleep
import os
import Owen
import csv
from datetime import datetime as dt

def getError() -> str:
    exc_type, exc_obj, exc_tb = sys.exc_info()
    return str(exc_type), str(exc_tb.tb_frame.f_code.co_filename), str(exc_tb.tb_lineno)

if os.name == 'nt':  # sys.platform == 'win32':
    from serial.tools.list_ports_windows import comports
elif os.name == 'posix':
    from serial.tools.list_ports_posix import comports

# класс, сканирующий порты на наличие нового устройства и отправляющий список новых устройств в основной класс через Qt Signal
class PortScaner(QtCore.QObject):
    newdevice_sign = QtCore.pyqtSignal(object)
    def __init__(self):
        super().__init__()
        self.list = set()

    def polling(self, time=1):
        lrunning = True
        while lrunning:
            if self.thread().isrunning == False:
                lrunning = False
            newlist = set(i.name for i in comports())

            if newlist != self.list:
                self.newdevice_sign.emit(newlist)

            self.list = newlist
            sleep(1)

        print("port thread exit")
        self.thread().exit()     


class DThread(QtCore.QThread):
    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.isrunning = True

    @QtCore.pyqtSlot(object)
    def event_handler(self, data):
        if data["name"] == self.name and data["action"] == "exit":
            self.isrunning = False
    
# класс, принимающий данные с контроллера и отправляющий их в основной класс через Qt Signal
class Controller(QtCore.QObject):
    dc_sgn = QtCore.pyqtSignal(int)
    rd_sgn = QtCore.pyqtSignal(object)
    def __init__(self, ser:serial.Serial):
        super().__init__()
        self.serial = ser
        ser.baudrate = 115200

    def polling(self):
        lrunning = True
        try:
            with self.serial:
                self.serial.readline()
                while lrunning:
                    if self.thread().isrunning == False:
                        lrunning = False
                    data = self.serial.readline().decode().rstrip()
                    self.rd_sgn.emit(data)
        except serial.serialutil.SerialException:
            self.dc_sgn.emit(1)
        except:
            self.dc_sgn.emit(1)
        try:
            self.serial.close()
        except:
            pass
        print('controller thread exit')
        self.thread().exit()

class Regulator(QtCore.QObject):
    dc_sgn = QtCore.pyqtSignal(int)
    rd_sgn = QtCore.pyqtSignal(object)
    def __init__(self, ser:serial.Serial):
        try:
            super().__init__()
            self.serial = serial.Serial(ser, timeout=3)
            self.serial.baudrate = 115200
            self.isHeating = False
            self.owenDevice = Owen.OwenDevice(self.serial, 0)
        except Exception as e:
            print(str(e))

    def set_temp(self, temp, speed):
        if isinstance(self.owenDevice, Owen.OwenDevice):
            try:
                self.owenDevice.writeFloat24("SP", temp)#self.sp_heater.value())
                self.owenDevice.writeFloat24("vSP", speed)#float(self.cmb_speed.currentText()))
            except serial.serialutil.SerialException:
                self.dc_sgn.emit(2)

    def get(self) -> float:
        try:
            while self.thread().isrunning:
                self.rd_sgn.emit({"type": "data", "val": self.owenDevice.getFloat24('PV')})
                sleep(1)
        except serial.serialutil.SerialException:
            self.dc_sgn.emit(2)
            print('regul err')
        except Owen.OwenProtocolError:
            print("Включите терморегулятор")
        except Exception as e:
            self.dc_sgn.emit(2)
            print(e)
        try:
            self.serial.close()
        except:
            pass
        print('heater thread exit')
        self.owenDevice = False
        self.thread().exit()

    def toggle_heater(self):
        if isinstance(self.owenDevice, Owen.OwenDevice):
            try:
                if self.isHeating:
                    self.owenDevice.writeChar('r-S', False)
                    self.isHeating = False
                else:
                    self.owenDevice.writeChar('r-S', True)
                    self.isHeating = True
                print(self.isHeating)
                self.rd_sgn.emit({"type": "heating", "val": self.isHeating})
            except serial.serialutil.SerialException:
                self.dc_sgn.emit(2)
            
        

class Ui(QtWidgets.QMainWindow):
    back_sign = QtCore.pyqtSignal(object)
    def __init__(self):
        super(Ui, self).__init__()
        uic.loadUi('design.ui', self)
        self.plotter = PlotWidget(self.plot_placehlder)
        self.gridplot = QtWidgets.QGridLayout(self.plot_placehlder)
        self.gridplot.addWidget(self.plotter, 1, 1, 1, 1)

        pyqtgraph.setConfigOption('background', 'y')
        pyqtgraph.setConfigOption('foreground', 'k')
        styles = {'color': 'black', 'font-size': '17px'}

        self.plotter.setBackground('w')
        self.plotter.showGrid(x=True, y=True)
        
        self.plotter.setMinimumSize(QtCore.QSize(300, 300))
        self.plot = self.plotter.plot()
        self.pen = pyqtgraph.mkPen(color=(255, 0, 0))
        self.pen2 = pyqtgraph.mkPen(color=(127, 0, 0))
        self.show()

        self.is_controller_connected, self.is_regulator_connected = False, False

        #start:work with portscanner
        self.portScanerThread = DThread("portscanner")
        self.portScanner = PortScaner()
        self.portScanner.moveToThread(self.portScanerThread)

        self.portScanerThread.started.connect(self.portScanner.polling)
        self.portScanner.newdevice_sign.connect(self.list_devices)
        self.portScanerThread.start()

        self.back_sign.connect(self.portScanerThread.event_handler)
        #end:work with portscanner

        self.btn_ioarduino.clicked.connect(self.startController)
        self.btn_ioregul.clicked.connect(self.startRegulator)
        self.btn_stoprecord.clicked.connect(self.saveMenu)
        self.btn_startrecord.clicked.connect(self.erase_data)

        self.erase_data()

        self.btn_eraseplot.clicked.connect(self.erase_data)
        self.cb_t13.stateChanged.connect(lambda: self.changeCheckBox(1))
        self.cb_t46.stateChanged.connect(lambda: self.changeCheckBox(4))
        self.cb_t79.stateChanged.connect(lambda: self.changeCheckBox(7))
        self.cb_t19.stateChanged.connect(lambda: self.changeCheckBox(9))

    def changeCheckBox(self, n):
        if n == 1:
            for i in (self.cb_t1, self.cb_t2, self.cb_t3):
                i.setChecked(self.cb_t13.isChecked())
        if n == 4:
            for i in (self.cb_t4, self.cb_t5, self.cb_t6):
                i.setChecked(self.cb_t46.isChecked())
        if n == 7:
            for i in (self.cb_t7, self.cb_t8, self.cb_t9):
                i.setChecked(self.cb_t79.isChecked())
        if n == 9:
            for i in (self.cb_t1, self.cb_t2, self.cb_t3, self.cb_t4, self.cb_t5, self.cb_t6, self.cb_t7, self.cb_t8, self.cb_t9):
                i.setChecked(self.cb_t19.isChecked())
        
        
    @QtCore.pyqtSlot(object)
    def list_devices(self, data):
        self.cmb_controller.clear()
        self.cmb_controller.addItems(list(data))

        self.cmb_regulator.clear()
        self.cmb_regulator.addItems(list(data))
        
        self.console.append(str(data))

    def print(self, *args):
        self.console.append(' '.join(map(str, args)))

    def erase_data(self):
        self.time = dt.now().timestamp()
        self.temp_data = [[] for i in range(11)]

    def saveMenu(self):
        with open(dt.now().strftime("%d.%m.%Y %H.%M.%S.csv"), 'w') as f:
            csvw = csv.writer(f)
            csvw.writerow(("base", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "datetime"))
            for i in range(len(self.temp_data[0])):
                csvw.writerow([self.temp_data[j][i] for j in range(11)])

    def closeEvent(self, e):
        with open(dt.now().strftime("Exit.csv"), 'w') as f:
            csvw = csv.writer(f)
            csvw.writerow(("base", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "datetime"))
            for i in range(len(self.temp_data[0])):
                csvw.writerow([self.temp_data[j][i] for j in range(11)])
        self.back_sign.emit({"name": "portscanner", "action": "exit"})
        self.back_sign.emit({"name": "controller", "action": "exit"})
        self.back_sign.emit({"name": "regulator", "action": "exit"})

    def startController(self, kill=False):
        try:
            if self.is_controller_connected or kill:
                self.back_sign.emit({"name": "controller", "action": "exit"})
                self.btn_ioarduino.setStyleSheet("background-color: rgb(255, 132, 128);")
                self.is_controller_connected = False
                del self.controller
            else:
                items = [self.cmb_controller.itemText(i) for i in range(self.cmb_controller.count())]
                #start:work with controller
                self.controllerThread = DThread("controller")
                self.controller = Controller(serial.Serial(items[self.cmb_controller.currentIndex()], timeout=1))
                self.controller.moveToThread(self.controllerThread)
                
                self.controllerThread.started.connect(self.controller.polling)
                self.back_sign.connect(self.controllerThread.event_handler)
                
                self.controller.rd_sgn.connect(self.show_temp)
                self.controller.dc_sgn.connect(self.device_disconnect)
                
                self.controllerThread.start()
                self.btn_ioarduino.setStyleSheet("background-color: rgb(170, 255, 155);")
                self.is_controller_connected = True
                #end:work with contoller
        except Exception as e:
            self.console.append(", ".join(getError()))

    def startRegulator(self):
        try:
            if self.is_regulator_connected:
                self.back_sign.emit({"name": "regulator", "action": "exit"})
                self.btn_ioregul.setStyleSheet("background-color: rgb(255, 132, 128);")
                self.is_regulator_connected = False
                self.btn_toggle.clicked.disconnect()
                del self.regulator
            else:
                items = [self.cmb_controller.itemText(i) for i in range(self.cmb_controller.count())]
                #start:work with regulator
                self.regulatorThread = DThread("regulator")
                self.regulator = Regulator(items[self.cmb_regulator.currentIndex()])
                self.regulator.moveToThread(self.regulatorThread)
                self.regulatorThread.started.connect(self.regulator.get)
                self.sp_heater.valueChanged.connect(self.update_owen)
                self.cmb_speed.currentIndexChanged.connect(self.update_owen)
                self.btn_toggle.clicked.connect(self.toggle_heater)

                self.back_sign.connect(self.regulatorThread.event_handler)

                self.regulator.rd_sgn.connect(self.get_owen)
                self.regulator.dc_sgn.connect(self.device_disconnect)
                
                self.regulatorThread.start()
                self.btn_ioregul.setStyleSheet("background-color: rgb(170, 255, 155);")
                self.is_regulator_connected = True
                
                #end:work with regulator
        except Exception as e:
            self.console.append(", ".join(getError()))

    def toggle_heater(self):
        if self.is_regulator_connected:
            self.regulator.toggle_heater()

    def update_owen(self):
        if self.is_regulator_connected:
            self.regulator.set_temp(self.sp_heater.value(), float(self.cmb_speed.currentText()))

    @QtCore.pyqtSlot(int)
    def device_disconnect(self, dev_id):
        if dev_id == 1:
            for index in range(10):
                self.plotter.plot([i for i in range(len(self.temp_data[index]))], self.temp_data[index], pen=self.pen)
            self.console.append("Controller disconected")
            self.btn_ioarduino.setStyleSheet("background-color: rgb(255, 132, 128);")
            self.is_controller_connected = False

        if dev_id == 2:
            self.console.append("Regulator disconected")
            self.btn_ioregul.setStyleSheet("background-color: rgb(255, 132, 128);")
            self.is_regulator_connected = False
            
    @QtCore.pyqtSlot(object)
    def get_owen(self, d:dict):
        if d["type"] == "data":
            self.ln_furtemp.setText(str(round(d["val"], 2)))
        elif d["type"] == "heating":
            if d["val"]:
                self.btn_toggle.setText("Греет")
                self.btn_toggle.setStyleSheet("background-color: rgb(170, 255, 155);")
            else:
                self.btn_toggle.setText("Не греет")
                self.btn_toggle.setStyleSheet("")
    
    @QtCore.pyqtSlot(object)
    def show_temp(self, data):
        if data == "":
            self.startController(True)
        show_ = []
        for i in (self.cb_t1, self.cb_t2, self.cb_t3, self.cb_t4, self.cb_t5, self.cb_t6, self.cb_t7, self.cb_t8, self.cb_t9):
            if i.isChecked():
                show_.append(1)
            else:
                show_.append(0)
        self.plotter.clear()
        try:
        
            for index, item in enumerate(data.split(',')):
                self.temp_data[index].append((0 if item=="None" else float(item)))
            self.temp_data[10].append(dt.now().timestamp()-self.time)
            if self.cmb_mode.currentIndex() == 0:
                for index in range(9):
                    if show_[index]:
                        self.plotter.plot(self.temp_data[10], self.temp_data[index+1], pen=self.pen)
                    self.plotter.plot(self.temp_data[10], self.temp_data[0], pen=self.pen2)
            else:
                for index in range(9):
                    if show_[index]:
                        self.plotter.plot(self.temp_data[0], [j-i for i, j in zip(self.temp_data[0], self.temp_data[index+1])], pen=self.pen2)

        except Exception as e:
            self.console.append(str(e))
        if self.temp_data:
            if max(self.temp_data, key=len) != min(self.temp_data, key=len):
                for i in range(10):
                    self.temp_data[i] = self.temp_data[i][: min(self.temp_data, key=len)]
                    self.console.append("bad input from controller")

app = QtWidgets.QApplication(sys.argv)
window = Ui()
print = window.print
app.exec_()
