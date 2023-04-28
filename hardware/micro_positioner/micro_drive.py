import pyvisa
from interface.dummy_interface import dummy_interface

import os
import time
import numpy as np
import atexit

import scipy.interpolate
from fnmatch import fnmatch
from collections import OrderedDict
from abc import abstractmethod
import re
from ctypes import cdll, c_int, c_uint, c_double

from core.module import Base
from core.configoption import ConfigOption
from interface.pulser_interface import PulserInterface, PulserConstraints, SequenceOption
from core.util.modules import get_home_dir

class MicroDrive(Base, dummy_interface):
    """
    H.Babashah - Hardware code for Madcity micro controlled used code from Madcitylab.
    """

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """
        H.Babashah - Inspired from Qudi - Initialisation performed during activation of the module.
        """
        path_to_dll = 'MicroDrive.dll' #fixme hardware/micro/
        self.madlib = cdll.LoadLibrary(path_to_dll)
        self.handler = self.mcl_start()
        atexit.register(self.mcl_close)

    def on_deactivate(self):
        """
        H.Babashah - Inspired from Qudi - Required tasks to be performed during deactivation of the module.
        """

        mcl_release_all = self.madlib['MCL_ReleaseAllHandles']
        mcl_release_all()

    def mcl_start(self):
        """
        Requests control of a single Mad City Labs Micro-Drive.

        Return Value:
            Returns a valid handle or returns 0 to indicate failure.
        """
        mcl_init_handle = self.madlib['MCL_InitHandle']

        mcl_init_handle.restype = c_int
        handler = mcl_init_handle()
        if (handler == 0):
            print("MCL init error")
            return -1
        return handler

    def mcl_close(self):
        """
        Releases control of all Nano-Drives controlled by this instance of the DLL.
        """
        mcl_release_all = self.madlib['MCL_ReleaseAllHandles']
        mcl_release_all()

    def mcl_microdrive_moveprofile_musteps(self, axis, velocity, microSteps):
        """
        Standard movement function.  Acceleration and deceleration ramps are generated for the specified motion.
        In some cases when taking smaller steps the velocity parameter may be coerced to its maximum achievable value.
        The maximum and minimum velocities can be found using MCL_MicroDriveInformation.

        @param: unsigned int axis: Which axis to move.  (X=1,Y=2,Z=3)
        @param: double velocity: Speed in mm/sec.
        @param: int microSteps: Number of microsteps to move the stage.
                                A positive number of microsteps  moves the stage toward its forward limit switch.
                                A negative number of microsteps moves it toward its reverse limit switch.
                                Zero will result in the axis not moving.

        @param: int handle

        @return: Returns MCL_SUCCESS or the appropriate error code.
        Error Codes  (pg. 21)
        MCL_SUCCESS			 0
        MCL_GENERAL_ERROR	-1
        MCL_DEV_ERROR		-2
        MCL_DEV_NOT_ATTACHED	-3
        MCL_USAGE_ERROR		-4
        MCL_DEV_NOT_READY	-5
        MCL_ARGUMENT_ERROR	-6
        MCL_INVALID_AXIS		-7
        MCL_INVALID_HANDLE	-8

        Notes:
        Care should be taken not to access the Micro-Drive while the microstage is moving for any reason other than stopping it.
        Doing so will adversely affect the internal timers of the Micro-Drive which generate the required step pulses for the specified movement. """
        mcl_micro_drive_move_profile_microsteps = self.madlib['MCL_MicroDriveMoveProfile_MicroSteps']
        mcl_micro_drive_move_profile_microsteps.restype = c_int
        error_code = mcl_micro_drive_move_profile_microsteps(c_uint(axis), c_double(velocity), c_int(microSteps),
                                                             c_int(self.handler))
        return error_code

    def MCL_MicroDriveMoveProfile(self, axis, velocity, distance, rounding):
        """
        Standard movement function.  Acceleration and deceleration ramps are generated for the specified motion. In some cases when taking smaller steps the velocity parameter may be coerced to its maximum achievable value. The maximum and minimum velocities can be found using MCL_MicroDriveInformation.

        Requirements: Specific to the following devices Micro-Drive(0x2500), NanoCyte MicroDrive(0x3500),
        and Micro-Drive3(0x2503)

        Parameters:
        axis		[IN]	Which axis to move.  (X=1,Y=2,Z=3)
        velocity		[IN]	Speed in mm/sec.
        distance		[IN]	Distance in mm to move the stage.  Positive distances move the stage toward its forward limit switch.
                                Negative distances move it toward its reverse limit switch.
                                A value of 0.0 will result in the axis not moving.
        rounding	[IN]	Determines how to round the distance parameter:
        					0 - Nearest microstep.
        					1 - Nearest full step.
        					2 - Nearest half step.
        handle		[IN]	Specifies which Micro-Drive to communicate with.

        Return Value:
        Returns MCL_SUCCESS or the appropriate error code.

        Notes:
        Care should be taken not to access the Micro-Drive while the microstage is moving for any reason other than stopping it. Doing so will adversely affect the internal timers of the Micro-Drive which generate the required step pulses for the specified movement.
        """
        mcl_microdrive_moveprofile = self.madlib['MCL_MicroDriveMoveProfile']
        mcl_microdrive_moveprofile.restype = c_int
        error_code = mcl_microdrive_moveprofile(c_uint(axis), c_double(velocity), c_double(distance), c_int(rounding),
                                                c_int(self.handler))
        return error_code