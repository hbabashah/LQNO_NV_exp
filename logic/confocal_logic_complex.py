from qtpy import QtCore
from collections import OrderedDict
import numpy as np
import time
import datetime
import matplotlib.pyplot as plt
from operator import not_
from logic.generic_logic import GenericLogic
from core.util.mutex import Mutex
from core.connector import Connector
from core.configoption import ConfigOption
from core.statusvariable import StatusVar
from threading import *
from scipy.optimize import curve_fit


class Confocallogiccomplex(GenericLogic):

    # Connectors
    nicard = Connector(interface='dummy_interface')
    mw_source = Connector(interface='dummy_interface')
    pulser= Connector(interface='dummy_interface')
    piezo= Connector(interface='dummy_interface')
    savelogic = Connector(interface='SaveLogic')
    taskrunner = Connector(interface='TaskRunner')
    fcw = StatusVar('fcw', 2.87e9)# CW frequency
    pcw = StatusVar('pcw', -10)# CW power
    fmin = StatusVar('fmin', 2.85e9)# sweep frequency min
    fmax = StatusVar('fmax', 2.89e9)# sweep frequency max
    fstep = StatusVar('fstep', 1e6)# sweep frequency step
    stime = StatusVar('stime', 0.001)# Step time
    xmin = StatusVar('xmin', 0)# sweep x min
    xmax = StatusVar('xmax', 1e-6)# sweep x max
    xnpts = StatusVar('xnpts', 10)# sweep x points
    ymin = StatusVar('ymin', 0)# sweep y min
    ymax = StatusVar('ymax', 1e-6)# sweep y max
    ynpts = StatusVar('ynpts', 10)# sweep y points
    xpos = StatusVar('xpos', 0)# x position
    ypos = StatusVar('ypos', 0)# y position
    zpos = StatusVar('zpos', 0)# z position
    mes_type = StatusVar('mes_type', 'PL')# stop time
    int_time = StatusVar('int_time', 20e-9)# integration time




    time_start = StatusVar('time_start', 0)# start time
    rabi_period = StatusVar('rabi_period', 100e-9)# start time
    navg = StatusVar('navg', 2)# number of averages
    threshold = StatusVar('threshold', 0.5)# sweep frequency min
    time_reference = StatusVar('time_reference', 1e-3)#  window time for reference
    time_signal = StatusVar('time_signal', 1e-3)# window time for signal
    time_reference_start = StatusVar('time_reference_start', 0.1e-6)# neglet time for signal
    time_signal_start = StatusVar('time_signal_start', 0.1e-6)# neglet time for reference
    npts = StatusVar('npts', 40)# number of points
    time_stop = StatusVar('time_stop', 0.001)# stop time




    # Update signals
    SigDataUpdated = QtCore.Signal(np.ndarray, np.ndarray)
    SigConfocalDataUpdated= QtCore.Signal(np.ndarray)
    SigConfocalArbDataUpdated= QtCore.Signal(np.ndarray)
    SigToggleAction= QtCore.Signal()
    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadlock = Mutex()

    def on_activate(self):
        self.Usepiezo = 0 # use piezo 1 or ni card 0
        # Get connectors
        self._mw_device = self.mw_source()
        self._nicard = self.nicard()
        self._pulser = self.pulser()
        self._piezo = self.piezo()
        self._save_logic = self.savelogic()
        self._taskrunner = self.taskrunner()

        """ Needs to be implemented
        # Get hardware constraints
        limits = self.get_hw_constraints()
        """

        self.data_freq = np.array([])
        self.data_spectrum = np.array([])

    def on_deactivate(self):
        """
        Deinitialisation performed during deactivation of the module.
        """
        # Disconnect signals
        #self.sigDataUpdated.disconnect()
        self._piezo.mcl_close()

    def start_data_acquisition(self):
        startThread = Thread(target=self.start_data_acquisition_thread)
        startThread.start()

    def start_data_acquisition_thread(self):
        with self.threadlock:
            # if self.module_state() == 'locked':
            #     self.log.error('Can not start Confocal scan. Logic is already locked.')
            #     return -1
            # self.module_state.lock()
            XvalueRange = np.linspace(self.xmin, self.xmax, int(self.xnpts))
            YvalueRange = np.linspace(self.ymin, self.ymax, int(self.ynpts))

            def exponenial_func(x, a, b, c):
                return a * (np.exp(-b * x))
            # self._scope.set_Center_Tscale(1, self.int_time / 1.25)  # 1.25*10
            # self._scope.set_trigger_sweep(0)  # set normal mode for ACQ of Oscope
            # self._scope.set_trigger_level(1)
            self.ChannelNumber = 1  # ACQ Chan Number

            # ChannelTrigNumber = 2  # ACQ_chan trigger
            # self._scope.set_trigger_source(ChannelTrigNumber)
            # self._pulser.set_confocal(0, 0)  # intialize the confocal
            # self._pulser.start_stream()  # start stream
            # self._scope.set_timeout()
            # self._scope.set_init_scale(1)
            # self._scope.set_scope_range(1, 3)
            # self._scope.set_Voffset(1, 1.5, 1)

            Image_xy = np.zeros((int(np.size(XvalueRange)), int(np.size(YvalueRange))))
            Image_xy_arb = np.zeros((int(np.size(XvalueRange)), int(np.size(YvalueRange))))

            # AutoVscale=True
            #Fixme change to direction_flag True toward right False towards left
            flag = True
            self._nicard.set_timing(self.int_time)
            self._mw_device.set_fcw(self.fcw)
            self.Laser_length = 100e-6
            self.Laser_length_s = int(np.ceil(self.Laser_length * self._nicard.get_timing()))

            var_sweep_type = 'linear'
            if self.time_start==0:
                self.time_start=10e-9
            if var_sweep_type == 'log':
                var_range = np.logspace(np.log10(self.time_start), np.log10(self.time_stop), self.npts,
                                        base=10)
            else:
                var_range = np.linspace(self.time_start, self.time_stop, int(self.npts))

            i = -1;
            for Xvalue in XvalueRange:
                i = i + 1
                j = 0
                if self.stop_acq == True:
                    break
                for Yvalue in YvalueRange:
                    if flag == False:
                        j = j - 1
                    # self._pulser.set_confocal(Xvalue, Yvalue)
                    t0 = time.time()
                    if self.Usepiezo==True:
                        self._piezo.gox(Xvalue)
                        self._piezo.goz(Yvalue)
                    else:
                        V_Xvalue=Xvalue/10
                        V_Yvalue=Yvalue/10
                        self._nicard.write_ao(np.array([V_Xvalue,V_Yvalue]))
                    if self.mes_type=='Contrast':
                        time.sleep(1e-3)
                        self._mw_device.set_status('OFF')
                    if self.mes_type == 'Contrast_fmax':
                        time.sleep(1e-3)
                        self._mw_device.set_fcw(self.fmax)
                        self._mw_device.set_status('ON')
                    #posread =self._piezo.get_position()
                    #print(Yvalue, posread[2])
                    #t1 = time.time()
                    #time.sleep(1e-3)  # make sure piezo is in the position and sgn is off

                    # self._pulser.start_stream()
                    #posread = self._piezo.get_position()
                    #print(Yvalue, posread[2])
                    #t2 = time.time() # 30 ms is enough for piezo to be sure that it is in the position
                    DATA = self._nicard.read_data()
                    #t3 = time.time()
                    Image_xy[i, j] = np.mean(DATA[self.ChannelNumber])
                    self.SigConfocalDataUpdated.emit(Image_xy)  # np.random.rand(5, 5)
                    Image_xy_arb[i, j] = np.mean(DATA[self.ChannelNumber])
                    if self.mes_type=='Contrast' or self.mes_type == 'Contrast_fmax':
                        self._mw_device.set_fcw(self.fcw) #for contrast fmax
                        self._mw_device.set_status('ON')
                        self.SigDataUpdated.emit(np.array(DATA[0]), np.array(DATA[self.ChannelNumber]))
                        time.sleep(1e-3)  # make sure sgn is on
                        DATA2 = self._nicard.read_data()
                        Image_xy_arb[i, j] = 1- np.mean(DATA2[self.ChannelNumber])/Image_xy[i, j]

                    print(self.mes_type)
                    if self.mes_type == 'T1' or self.mes_type == 'Rabi' or self.mes_type == 'Ramsey' or self.mes_type == 'Hahn_echo':
                        print('start pulse measurement')
                        if self.mes_type == 'Rabi' or self.mes_type == 'Ramsey' or self.mes_type == 'Hahn_echo':
                            self._mw_device.set_status('ON')
                            time.sleep(1e-3)
                        VARResult = []
                        ii = 0
                        for variable in var_range:
                            if self.stop_acq == True:
                                break
                            self._nicard.set_refrence_trigger('Falling',self.Laser_length_s)
                            self._nicard.set_pause_trigger('Low')

                            #self._pulser.set_pulse_measurement(self.Laser_length,10e-6, 'T1', 2e-6)
                            print(self.mes_type)
                            self._pulser.set_pulse_measurement(self.Laser_length,variable, self.mes_type, self.rabi_period)
                            self._pulser.start_stream()
                            #print(self.Laser_length_s)
                            print('HERE')
                            DATA = self._nicard.read_data()
                            print(DATA)

                            DATAavg=np.zeros(self.Laser_length_s)
                            PulseAmp, PulseTime =np.array(DATA[self.ChannelNumber]), DATA[0]
                            for jj in range(int(np.floor(np.size(PulseAmp) / self.Laser_length_s))):
                                DATAavg = DATAavg + PulseAmp[jj * self.Laser_length_s:jj * self.Laser_length_s + self.Laser_length_s]

                            #               Analysis

                            # set min as zero

                            maxindPulseAmp = np.argmax(PulseAmp)
                            maxPulseAmpAvg = abs(np.mean(PulseAmp[int(maxindPulseAmp):int(maxindPulseAmp + 100)]))
                            PulseAmp = [kar / abs(maxPulseAmpAvg) for kar in PulseAmp]

                            TimeRes = PulseTime[4] - PulseTime[3]
                            IntTimeSampleSignal = int(np.floor(self.time_signal / TimeRes))
                            IntTimeSampleReference = int(np.floor(self.time_reference / TimeRes))
                            IntTimeSampleSignalStart = int(np.floor(self.time_signal_start / TimeRes))
                            IntTimeSampleReferenceStart = int(np.floor(self.time_reference_start / TimeRes))
                            ind_L_pulseAmp = 0
                            ind_R_pulseAmp = self.Laser_length_s-1
                            Ssample = PulseAmp[ind_L_pulseAmp:ind_L_pulseAmp + IntTimeSampleSignal]
                            Rsamples = PulseAmp[ind_R_pulseAmp - IntTimeSampleReference:ind_R_pulseAmp]
                            print(ind_R_pulseAmp - IntTimeSampleReference-ind_R_pulseAmp)
                            Signal = np.trapz(Ssample, dx=5) / (np.size(Ssample) - 1)  # Signal Window
                            Reference = np.trapz(Rsamples, dx=5) / (np.size(Rsamples) - 1)  # Reference Window

                            VARResult.append(Signal / Reference)
                            ii = ii + 1
                            self.SigDataUpdated.emit(var_range[0:ii], np.array(VARResult))
                            #print(DATAavg)
                            #self.SigDataUpdated.emit(np.array(range(0,len(DATAavg),1)), np.array(DATAavg))


                        if self.mes_type=='T1':
                            popt, pcov = curve_fit(exponenial_func, var_range, VARResult, p0=(.01, 1e-3, 1), maxfev=10000)

                        #fittedx = np.linspace(var_range[0], var_range[np.size(var_range) - 1], 1000)
                        #fittedy = exponenial_func(fittedx, *popt)

                            Image_xy_arb[i, j] =np.array(round(1 / popt[1] * 1e3, 2))
                        else:
                            Image_xy_arb[i, j] = np.array(np.mean(VARResult))
                    if self.mes_type == 'PL':
                        self.SigDataUpdated.emit(np.array(DATA[0]), np.array(DATA[self.ChannelNumber]))
                        time.sleep(1e-3)  # make sure sgn is on
                    self.SigConfocalArbDataUpdated.emit(Image_xy_arb)  # np.random.rand(5, 5)
                    if flag == True:
                        j = j + 1
                    if self.stop_acq == True:
                        break

                    t4 = time.time()
                    if self.Usepiezo==1:
                        posread = self._piezo.get_position()
                        print(Yvalue, posread[2])
                    #print(t1-t0, t2-t1, t3-t2, t4-t3)

                YvalueRange = np.flip(YvalueRange)
                flag = not_(flag)
            self._mw_device.set_status('OFF')
            self.SigToggleAction.emit()
            # if self.module_state() == 'locked':
            #     self.module_state.unlock()
            #     return -1



    def set_cordinate_sparam(self,xmin,xmax,xnpts,ymin,ymax,ynpts):
        self.xmin = xmin*1e6
        self.xmax = xmax*1e6
        self.xnpts = xnpts
        self.ymin = ymin*1e6
        self.ymax = ymax*1e6
        self.ynpts = ynpts

    def set_move_to_position(self, xpos, ypos,zpos):
        self.xpos = xpos*1e6
        self.ypos = ypos*1e6
        self.zpos = zpos*1e6

    def move_to_position(self):
        if self.Usepiezo==1:
            self._piezo.gox(self.xpos) # in um
            self._piezo.goz(self.ypos)
            self._piezo.goy(self.zpos)
        else:
            self._nicard.set_timing(self.int_time)
            V_Xvalue = self.xpos / 10
            V_Yvalue = self.ypos / 10
            self._nicard.write_ao(np.array([V_Xvalue, V_Yvalue]))

        #print(self._piezo.get_position())
        # self._pulser.set_confocal(self.xpos, self.ypos)
        # self._scope.set_Center_Tscale(1, self.int_time / 1.25)  # 1.25*10
        # self._scope.set_trigger_sweep(0)  # set normal mode for ACQ of Oscope
        # self._pulser.start_stream()
        #
        # self._scope.set_scope_range(1, 3)
        # self._scope.set_Voffset(1, 1.5, 1)
        # self.ChannelNumber=1
        self.ChannelNumber = 1
        self._nicard.set_timing(self.int_time)
        DATA = self._nicard.read_data()
        self.SigDataUpdated.emit(np.array(DATA[0]), np.array(DATA[self.ChannelNumber]))

    def set_fcw(self, fcw):
        self.fcw = fcw
        self._mw_device.set_fcw(self.fcw)



    def stop_data_acquisition(self,state):
        #Fix me mutex threadlock might be required to add
        # if self.module_state() == 'locked':
        #     self.module_state.unlock()
        #     return -1
        self.stop_acq = True


    def set_pcw(self, pcw):
        self._mw_device.set_pcw(pcw)
        self.pcw = pcw
    def set_ODMR(self, stime,npts):
       # self._pulser.set_ODMR(stime,npts)
      #  self._mw_device.set_ODMR(stime,npts)
        self.stime = stime
        self.npts = npts

    def set_sweep_param(self, fmin,fmax,fstep):
        self._mw_device.set_sweep_param(fmin,fmax,fstep)
        self.fmin = fmin
        self.fmax = fmax
        self.fstep = fstep
    def set_scope_param(self,int_time,navg):

        self.int_time = int_time
        self.navg = navg
        # self._scope.set_Center_Tscale(1, int_time / 1.25)  # 1.25*10
        # if navg==1:
        #     self._scope.set_acquisition_type(0)  # Normal
        # else:
        #     self._scope.set_acquisition_type(1)  # AVG type ACQ
        #     self._scope.set_acquisition_count(self.navg)  # set the number of avg for oscope
    def set_mes_type(self, mes_type):

        self.mes_type=mes_type
        print(mes_type)
    def ThresholdL(self,data,t_v):

        t_ind = 0
        for kop in range(len(data)) :
            if data[kop] >= t_v :
                t_ind = kop
                break
        if t_ind==0:
            print('Probably could not find the begining of the pulse, zero set as begining')
        return t_ind

    def ThresholdR(self,data,t_v):

        t_ind = -1
        for kop in range(len(data)) :
            if data[-kop-1] >= t_v :
                t_ind = -kop-1
                break
        if t_ind==-1:
            print('Probably could not find the begining of the pulse, zero set as begining')
        return t_ind
    def set_navg(self, navg):

        self.navg = navg
    def set_pulse(self, time_start,time_stop,npts,rabi_period):
        self.time_start = time_start
        self.time_stop = time_stop
        self.npts = npts
        self.rabi_period=rabi_period
    def set_pulse_analysi_param(self, threshold,time_reference,time_signal,time_reference_start,time_signal_start):

        self.threshold = threshold
        self.time_reference = time_reference
        self.time_signal = time_signal
        self.time_reference_start = time_reference_start
        self.time_signal_start = time_signal_start