import copy
import numpy as np
import ctypes
import time
import PyDAQmx as daq

from core.module import Base
from core.configoption import ConfigOption
from core.util.helpers import natural_sort
from interface.data_instream_interface import DataInStreamInterface, DataInStreamConstraints
from interface.dummy_interface import dummy_interface

from interface.process_control_interface import ProcessControlInterface
from interface.data_instream_interface import StreamingMode, StreamChannelType, StreamChannel


class NICard_Acquisition(Base, dummy_interface):
    """
    H.babashah - NI card hardware for continuous acquisition on analog inputs
    """

    # config options
    _device_name_slow = ConfigOption(name='device_name_slow', default='Dev1', missing='warn')
    _device_name_fast = ConfigOption(name='device_name_fast', default='Dev3', missing='warn')
    _analog_inputs = ConfigOption(name='analog_inputs', default=list(), missing='warn')
    _analog_outputs = ConfigOption(name='analog_outputs', default=list(), missing='warn')
    _trigger_terminal = ConfigOption(name='trigger_terminal', default='PFI8', missing='info')
    _sampling_frequency_slow = ConfigOption(name='sampling_frequency_slow', default=200*10**3, missing='info')
    _sampling_frequency_fast = ConfigOption(name='sampling_frequency_fast', default=200*10**3, missing='info')


    def on_activate(self):
        """
        H.babashah - Creates and starts the continuous acquisition task. If buffer is full, all non-used data will be automatically destroyed.
        """
        # Create the acquisition task
        self._ai_task = daq.TaskHandle()
        self._ao_task = daq.TaskHandle()
        self.counter_in_task = daq.TaskHandle()
        self.counter_out_task = daq.TaskHandle()
        self.read = daq.int32()
        self.samplesWritten = daq.int32()

        daq.DAQmxCreateTask("", daq.byref(self._ai_task))
        daq.DAQmxCreateTask("", daq.byref(self._ao_task))
        daq.DAQmxCreateTask("", daq.byref(self.counter_in_task))
        daq.DAQmxCreateTask("", daq.byref(self.counter_out_task))
        # Create the list of channels to acquire
        self.nb_chan = 0
        print(self._device_name_fast)
        for channel in self._analog_inputs:
            daq.CreateAIVoltageChan(self._ai_task, self._device_name_fast + '/' + channel, None, daq.DAQmx_Val_RSE, -10,
                                    10, daq.DAQmx_Val_Volts, None)  # RSE or NRSE or Diff
            self.nb_chan += 1

        self.nb_chan_ao = 0
        for channel in self._analog_outputs:
            daq.CreateAOVoltageChan(self._ao_task, self._device_name_slow + '/' + channel, None, -10, 10,
                                    daq.DAQmx_Val_Volts, None)  # RSE or NRSE or Diff
            self.nb_chan_ao += 1
        if self.nb_chan_ao:
            self.outputRate = 1000
            self.numSamples = 2
            # daq.CfgSampClkTiming(self._ao_task,'', self.outputRate, daq.DAQmx_Val_Rising,
            #                       daq.DAQmx_Val_FiniteSamps, self.numSamples)

        ##################################
        self.ch2 = '/Dev3/Ctr1'
        ##################################
        self.counter_channel = '/Dev3/PFI1'
        ##################################
        daq.CreateCISemiPeriodChan(self.counter_in_task,
                                   self.ch2,
                                   'Counter Channel 1',  # The name to assign to the created virtual channel.
                                   0,  # Expected minimum count value
                                   2,  # Expected maximum count value
                                   daq.DAQmx_Val_Ticks,
                                   # The units to use to return the measurement. Here are timebase ticks
                                   '')

        my_clock_channel = '/Dev3/Ctr2'
        duty_cycle = 0.5
        daq.CreateCOPulseChanFreq(self.counter_out_task, my_clock_channel,
                                  "myClockTask",
                                  daq.DAQmx_Val_Hz,
                                  daq.DAQmx_Val_Low,
                                  0,
                                  self._sampling_frequency_slow / 2,  # semiperiodic resolution
                                  duty_cycle,
                                  )

        daq.CfgImplicitTiming(self.counter_out_task,
                              daq.DAQmx_Val_ContSamps,
                              1000  # the buffer size
                              )

        daq.SetCISemiPeriodTerm(self.counter_in_task,  # Sync
                                self.ch2,  # assign a named Terminal
                                my_clock_channel + 'InternalOutput')

    def on_deactivate(self):
        daq.DAQmxStopTask(self._ai_task)
        daq.DAQmxClearTask(self._ai_task)
        daq.DAQmxStopTask(self.counter_in_task)
        daq.DAQmxClearTask(self.counter_in_task)
        daq.DAQmxStopTask(self.counter_out_task)
        daq.DAQmxClearTask(self.counter_out_task)

    def set_timing(self, acquisition_time):
        """ H.Babashah - Define the timing of the acquisition. """
        self._acquisition_time = acquisition_time
        self.nb_samps_per_chan = int(self._acquisition_time * self._sampling_frequency_slow)
        self._buffer_size = int(self._acquisition_time * self._sampling_frequency_slow * self.nb_chan)
        self.raw_data = np.zeros(int(self._buffer_size))
        daq.CfgSampClkTiming(self._ai_task, '', int(self._sampling_frequency_slow), daq.DAQmx_Val_Rising,
                             daq.DAQmx_Val_FiniteSamps, self.nb_samps_per_chan)

        self.data = np.ndarray(
            (self.nb_chan + 2, self.nb_samps_per_chan))  # nb of rows: +1 for time, +1 for digital channel

        ###################################################
        ##          Counting
        ###################################################

        ##################################
        daq.SetCICtrTimebaseSrc(self.counter_in_task, self.ch2, self.counter_channel)

        daq.CfgImplicitTiming(self.counter_in_task, daq.DAQmx_Val_ContSamps,
                              2 ** 25
                              # 2**30 is maximum. buffer length which stores  temporarily the number of generated samples
                              )

        self.samples = int(np.ceil(acquisition_time * self._sampling_frequency_slow / 2))

    def start_counting(self):
        '''

        :return:
        '''
        daq.DAQmxStartTask(self.counter_out_task)
        daq.DAQmxStartTask(self.counter_in_task)

    def stop_counting(self):
        '''

        :return:
        '''
        daq.DAQmxStopTask(self.counter_out_task)
        daq.DAQmxStopTask(self.counter_in_task)

    def get_timing(self):
        return self._sampling_frequency_slow

    def set_trigger(self, edge):
        """ H.Babashah - Define the edge of the external trigger. """

        if edge == 'Rising':
            daq.CfgDigEdgeStartTrig(self._ai_task, self._trigger_terminal, daq.DAQmx_Val_Rising)
        elif edge == 'Falling':
            daq.CfgDigEdgeStartTrig(self._ai_task, self._trigger_terminal, daq.DAQmx_Val_Falling)

    def set_pause_trigger(self, when):
        """ H.Babashah - it stop acquiring the data while triggered. """

        daq.SetPauseTrigType(self._ai_task,
                             daq.DAQmx_Val_DigLvl)  # Pause the measurement or generation while a digital signal is at either a high or low state.
        daq.SetDigLvlPauseTrigSrc(self._ai_task,
                                  self._trigger_terminal)  # Specifies the name of a terminal where there is a digital signal to use as the source of the Pause Trigger.
        if when == 'High':
            daq.SetDigLvlPauseTrigWhen(self._ai_task,
                                       daq.DAQmx_Val_High)  # Specifies whether the task pauses while the signal is high or low
        elif when == 'Low':
            daq.SetDigLvlPauseTrigWhen(self._ai_task,
                                       daq.DAQmx_Val_Low)  # Specifies whether the task pauses while the signal is high or low
        '''
        daq.SetPauseTrigType(self.counter_out_task,
                             daq.DAQmx_Val_DigLvl)  # Pause the measurement or generation while a digital signal is at either a high or low state.
        daq.SetDigLvlPauseTrigSrc(self.counter_out_task,
                                  self._trigger_terminal)  # Specifies the name of a terminal where there is a digital signal to use as the source of the Pause Trigger.
        if when == 'High':
            daq.SetDigLvlPauseTrigWhen(self.counter_out_task,
                                       daq.DAQmx_Val_High)  # Specifies whether the task pauses while the signal is high or low
        elif when == 'Low':
            daq.SetDigLvlPauseTrigWhen(self.counter_out_task,
                                       daq.DAQmx_Val_Low)  # Specifies whether the task pauses while the signal is high or low
        '''
    def set_refrence_trigger(self, edge, pretriggerSamples):
        """ H.Babashah - It acquire the data before the trigger """
        if edge == 'Rising':
            daq.CfgDigEdgeRefTrig(self._ai_task, self._trigger_terminal, daq.DAQmx_Val_Rising,
                                  pretriggerSamples)  # C channel DDG

        elif edge == 'Falling':
            daq.CfgDigEdgeRefTrig(self._ai_task, self._trigger_terminal, daq.DAQmx_Val_Falling,
                                  pretriggerSamples)  # C channel DDG

    def set_arm_start_trigger(self):

        daq.SetArmStartTrigType(self.counter_in_task, daq.DAQmx_Val_DigEdge)  #############################Changed
        daq.SetDigEdgeArmStartTrigSrc(self.counter_in_task,
                                      self._trigger_terminal)  #############################Changed
        daq.SetDigEdgeArmStartTrigEdge(self.counter_in_task, daq.DAQmx_Val_Rising)  #############################Changed

    def start_acquisition(self):
        """ H.Babashah - Start the acquisition task.
        It seems that using the start task generates an error when trying to read data several times for "continuous acquisition".
        Only calling read several times seems fine. """
        pass  # daq.DAQmxStartTask(self._ai_task)

    def stop_acquisition(self):
        daq.DAQmxStopTask(self._ai_task)

    def read_data(self):
        ''''

        '''
        time_data = np.linspace(0, self._acquisition_time, int(self.nb_samps_per_chan))
        t0 = time.time()
        daq.ReadAnalogF64(self._ai_task, self.nb_samps_per_chan, 150, daq.DAQmx_Val_GroupByChannel, self.raw_data,
                          self._buffer_size, ctypes.byref(self.read), None)
        t1 = time.time()
        print(t1 - t0)
        self.data[0] = time_data
        for i in range(self.nb_chan):
            self.data[i + 1] = np.split(self.raw_data, self.nb_chan)[i]

        n_read_samples = daq.int32()
        _RWTimeout = 10

        count_data = np.empty((1, 2 * self.samples), dtype=np.uint32)

        daq.ReadCounterU32(self.counter_in_task, 2 * self.samples,
                           _RWTimeout,
                           count_data[0],
                           2 * self.samples,
                           ctypes.byref(n_read_samples),
                           None)  #
        self.data[-1, :] = count_data[0,
                           :] * self._sampling_frequency_slow  # by convention, data from digital channel is stored in last row
        print('count')
        print(sum(count_data[0, :]))
        print(self.data[-1, :].max())
        print(self._acquisition_time)
        print(np.shape(count_data[0, :]))
        print(np.shape(self.data))
        return self.data

    def write_ao(self, ao_value):

        self._ao_value = ao_value
        self._ao_value = np.vstack((self._ao_value, self._ao_value))
        self._ao_value = self._ao_value.transpose()
        self._ao_value = np.require(self._ao_value, np.double, ['C', 'W'])

        daq.WriteAnalogF64(self._ao_task, numSampsPerChan=self.numSamples, autoStart=True, timeout=1.0,
                           dataLayout=daq.DAQmx_Val_GroupByChannel, writeArray=self._ao_value, reserved=None,
                           sampsPerChanWritten=ctypes.byref(self.samplesWritten))

        #
        # Counter1.SetArmStartTrigType(daq.DAQmx_Val_DigEdge)           #############################Changed
        # Counter1.SetDigEdgeArmStartTrigSrc("PFI2")#############################Changed
        # Counter1.SetDigEdgeArmStartTrigEdge(daq.DAQmx_Val_Rising)#############################Changed
        # Counter2.SetArmStartTrigType(daq.DAQmx_Val_DigEdge)#############################Changed
        # Counter2.SetDigEdgeArmStartTrigSrc("PFI2")#############################Changed
        # Counter2.SetDigEdgeArmStartTrigEdge(daq.DAQmx_Val_Rising)#############################Changed


# def Acquire(ChanName, Filepath, Save=1, ACQtime=1, LaserLength=200e-6, Resolution=0.5e-6):
#     # ACQtime=1
#     # LaserLength=200e-6
#     # Resolution =0.5e-6  # it should be in seconds(100 ns resolution is the max)
#
#     Start = time.time()
#     print("Acquiring signalTrig(s)...\n")
#
#     DATA = {}
#     flag = 0
#     flag2 = 1
#     split = 2
#     SLaserLength = int(LaserLength / Resolution)
#     while flag == 0:
#         if ACQtime > split:
#             ACQtimeSub = split
#             ACQtime = ACQtime - split
#         else:
#             ACQtimeSub = ACQtime
#             flag = 1
#
#         Counter1 = daq.Task()
#         Counter2 = daq.Task()
#         read2 = daq.c_uint64()
#
#         Clock = daq.Task()
#         read = daq.c_ulong()
#         rate = 1000
#         n_samples = 1000
#         duty_cycle = 0.5
#         _RWTimeout = 100
#
#         n_read_samples = daq.int32()
#
#         period = Resolution * 2
#         samples = int(np.ceil(ACQtimeSub / period))
#
#         count_data = np.empty((1, 2 * samples), dtype=np.uint32)
#         count_data2 = np.empty((1, 2 * samples), dtype=np.uint32)
#
#         my_clock_channel = '/Dev1/Ctr2'
#         Clock.CreateCOPulseChanFreq(my_clock_channel,
#                                     "myClockTask",
#                                     daq.DAQmx_Val_Hz,
#                                     daq.DAQmx_Val_Low,
#                                     0,
#                                     1 / float(period),
#                                     duty_cycle,
#                                     )
#
#         Clock.CfgImplicitTiming(
#             daq.DAQmx_Val_ContSamps,
#             1000  # the buffer size
#         )
#
#         Clock.SetPauseTrigType(
#             daq.DAQmx_Val_DigLvl)  # Pause the measurement or generation while a digital signal is at either a high or low state.
#         Clock.SetDigLvlPauseTrigSrc(
#             "PFI2")  # Specifies the name of a terminal where there is a digital signal to use as the source of the Pause Trigger.
#         Clock.SetDigLvlPauseTrigWhen(
#             daq.DAQmx_Val_Low)  # Specifies whether the task pauses while the signal is high or low
#
#         ch2 = '/Dev1/Ctr1'
#         Counter2.CreateCISemiPeriodChan(
#             ch2,
#             'Counter Channel 1',  # The name to assign to the created virtual channel.
#             0,  # Expected minimum count value
#             2,  # Expected maximum count value
#
#             daq.DAQmx_Val_Ticks,  # The units to use to return the measurement. Here are timebase ticks
#             ''
#         )
#         Counter2.SetCISemiPeriodTerm(  # Sync
#             ch2,  # assign a named Terminal
#             '/Dev1/Ctr2' + 'InternalOutput')
#         Counter2.SetCICtrTimebaseSrc(ch2,
#                                      '/Dev1/PFI2')
#
#         Counter2.CfgImplicitTiming(daq.DAQmx_Val_ContSamps,
#                                    2 ** 25
#                                    # 2**30 is maximum. buffer length which stores  temporarily the number of generated samples
#                                    )
#
#         Counter1.CreateCISemiPeriodChan(
#             '/Dev1/Ctr0',  # use this counter channel. The name of the counter to use to create virtual channels.
#             'Counter Channel 1',  # The name to assign to the created virtual channel.
#             0,  # Expected minimum count value
#             2,  # Expected maximum count value
#
#             daq.DAQmx_Val_Ticks,  # The units to use to return the measurement. Here are timebase ticks
#             ''  # customScaleName, in case of different units(DAQmx_Val_FromCustomScale).
#         )
#
#         Counter1.SetCISemiPeriodTerm(
#             '/Dev1/Ctr0',
#             '/Dev1/Ctr2' + 'InternalOutput')
#
#         Counter1.SetCICtrTimebaseSrc('/Dev1/Ctr0',
#                                      '/Dev1/PFI1')
#
#         Counter1.CfgImplicitTiming(daq.DAQmx_Val_ContSamps,
#                                    2 ** 25
#                                    # 2**30 is maximum.
#                                    )
#
#         Counter1.SetArmStartTrigType(daq.DAQmx_Val_DigEdge)  #############################Changed
#         Counter1.SetDigEdgeArmStartTrigSrc("PFI2")  #############################Changed
#         Counter1.SetDigEdgeArmStartTrigEdge(daq.DAQmx_Val_Rising)  #############################Changed
#         Counter2.SetArmStartTrigType(daq.DAQmx_Val_DigEdge)  #############################Changed
#         Counter2.SetDigEdgeArmStartTrigSrc("PFI2")  #############################Changed
#         Counter2.SetDigEdgeArmStartTrigEdge(daq.DAQmx_Val_Rising)  #############################Changed
#         try:
#             Counter1.StartTask()
#             Counter2.StartTask()
#         # print('1')
#         # time.sleep(0.1)
#         except Exception as e:
#             print('exception Happened')
#             print(e)
#             Clock.StopTask()
#             Clock.ClearTask()
#         Clock.StartTask()
#
#         n_read_samples = daq.int32()
#
#         count_data = np.empty((1, 2 * samples), dtype=np.uint32)
#         count_data2 = np.empty((1, 2 * samples), dtype=np.uint32)
#
#         Counter1.ReadCounterU32(2 * samples,
#                                 _RWTimeout,
#                                 count_data[0],
#                                 2 * samples,
#                                 byref(n_read_samples),
#                                 None)
#
#         Counter2.ReadCounterU32(2 * samples,
#                                 _RWTimeout,
#                                 count_data2[0],
#                                 2 * samples,
#                                 byref(n_read_samples),
#                                 None)  #
#
#         Laser = count_data[0, :]
#         Sync = count_data2[0, :]
#         # pl.close('all')
#         # pl.plot(Sync,'b+')
#         # pl.figure()
#         # pl.plot(Laser,'b+')
#         try:
#             Counter1.StopTask()
#             Counter1.ClearTask()
#             Counter2.StopTask()
#             Counter2.ClearTask()
#             Clock.StopTask()
#             Clock.ClearTask()
#
#             # print('task stoped1')
#         except:
#             pass
#         a = np.argwhere(Sync > 0.5)
#         #############################Changed
#         ArraySize = np.min(np.diff(np.transpose(a))) - 1
#         mydata = np.zeros(ArraySize)
#         if flag2 == 1:
#             mydataMain = np.zeros(ArraySize)
#             flag2 = 0
#
#         for i in range(np.size(a) - 2):
#             if i != int(np.size(a)) - 1:
#                 mydata = mydata + Laser[int(a[i]) + 1:int(a[i]) + ArraySize + 1]
#         mydataMain = mydataMain + mydata
#
#     print("Signal of " + str(np.size(a)) + " pulses acquired in " + str(round(time.time() - Start, 2)) + "s.\n")
#
#     # pl.figure()
#     # pl.plot(1e6*Resolution*np.arange(np.size(mydata)),mydata)
#
#     DATA[ChanName] = list(mydataMain)
#     DATA['TimeScale'] = list(Resolution * np.arange(np.size(mydataMain)))
#
#     # Saving DATA under .txt :
#     if Save == 1:
#         # Saving data #
#         os.makedirs(os.path.dirname(Filepath), exist_ok=True)
#         with open(Filepath, 'a') as f:
#             print(DATA, file=f)
#             time.sleep(1)
#
#     return DATA[ChanName], DATA['TimeScale']
#     # return mydata, Resolution*np.arange(np.size(mydata))
