import csv
import datetime
import os
import subprocess
import sys
import time

import mysql.connector as mdb
import numpy as np
from toptica.lasersdk.dlcpro.v2_0_3 import DLCpro, NetworkConnection, DeviceNotFoundError

from PID import PID


def dlcpro_connect(ip):
    try:
        dlcpro = DLCpro(NetworkConnection(ip))
        print('DLCpro connected')
        return dlcpro
    except DeviceNotFoundError:
        sys.stderr.write('Device not found')


def create_connection(host_name, user_name, user_password, database):
    conn = None
    try:
        conn = mdb.connect(
            host=host_name,
            user=user_name,
            passwd=user_password,
            database=database
        )
        print("Connection to MySQL DB successful")
    except mdb.Error as e:
        print(f"The error '{e}' occurred")
    return conn


# Get the number of channels from the cvs file
def getChannels():
    const = [0 for i in range(16)]
    with open('setpoints.csv', 'r+') as csvfile:
        reader = csv.reader(csvfile, delimiter=' ')
        for row in reader: pass
        Channels = int(row[2])
    return Channels


# Get the set points of the laser from the server
def getSetpoints():
    cur.execute("SELECT * FROM `wavemeter`.`setpoint`")
    rows = cur.fetchall()
    if (len(rows) > 0):
        return rows[0]
    else:
        return None


# Read the wavemeter
def getFreqs():
    # Channels = getChannels()
    name = "WavemeterData.exe "
    name = name + str(Channels)
    with open(os.devnull, "w") as fnull:
        test = subprocess.call(name, stdout=fnull,
                               shell=True)  # Added shell True to avoid the shell to pop out, GP 11/15
    waveOut = subprocess.check_output(name, shell=True).decode('utf-8').split(
        " ")  # Added shell True to avoid the shell to pop out, GP 11/15

    return [float(freq) for freq in waveOut[0:Channels]]


def getErrors():
    # Channels = getChannels()
    freqError = [0 for i in range(Channels)]
    setPoints = getSetpoints()
    freqAct = getFreqs()
    for j in range(Channels):
        freqError[j] = freqAct[j] - setPoints[j]
    return freqError


def Lock(ip_dlcpro='10.128.11.46'):
    try:
        with DLCpro(NetworkConnection('10.128.11.46')) as dlcpro:

            setPoints = getSetpoints()

            offset_369 = 47.893991  # Offset in Volts
            offset_399 = 0
            offset_935 = 0

            GlobalGain369 = 1
            GlobalGain399 = 18
            GlobalGain935 = 30

            integr369 = 400
            integr399 = 300
            integr935 = 500

            LaserLock_369 = PID(P=200, I=integr369, D=0)
            LaserLock_399 = PID(P=300, I=integr399, D=0)
            LaserLock_935 = PID(P=350, I=integr935, D=0)

            LaserLock_369.setPoint(setPoints[0])
            LaserLock_399.setPoint(setPoints[1])
            LaserLock_935.setPoint(setPoints[2])

            dlcpro.laser1.dl.pc.voltage_set.set(offset_369)

            while True:
                freq = getFreqs()

                # Update setpoints
                t = getSetpoints()
                if (t != None):
                    setPoints = getSetpoints()
                    if (LaserLock_369.set_point != setPoints[0]): LaserLock_369.setPoint(setPoints[0])
                    if (LaserLock_399.set_point != setPoints[1]): LaserLock_399.setPoint(setPoints[1])
                    if (LaserLock_935.set_point != setPoints[2]): LaserLock_935.setPoint(setPoints[2])

                # Set the error to zeros for wave meter channels which are not used or not well exposed
                for i in range(len(freq)):
                    if freq[i] < 0:
                        freq[i] = setPoints[i]

                # Update lock status
                lock_369 = setPoints[3]
                lock_399 = setPoints[4]
                lock_935 = setPoints[5]

                if (lock_369 != 0):
                    LaserLock_369.setKi(integr369)
                    error_369 = LaserLock_369.update(freq[0])
                    # print ("error 369 = ",error_369)
                else:
                    LaserLock_369.setKi(0)
                    LaserLock_369.setIntegrator(0)
                    error_369 = 0

                if (lock_399 != 0):
                    LaserLock_399.setKi(integr399)
                    error_399 = LaserLock_399.update(freq[1])
                    # print ("error 399 = ",error_399)
                else:
                    LaserLock_399.setKi(0)
                    LaserLock_399.setIntegrator(0)
                    error_399 = 0

                if (lock_935 != 0):
                    LaserLock_935.setKi(integr935)
                    error_935 = LaserLock_935.update(freq[2])
                    # print ("error 935 = ",error_935)
                else:
                    LaserLock_935.setKi(0)
                    LaserLock_935.setIntegrator(0)
                    error_935 = 0

                # print("freq = ", freq)
                print("delta = ", freq[0] - setPoints[0])
                print("error = ", error_369)

                # update lock broken status
                max_error = 5
                if (np.absolute(error_369) >= max_error):
                    print("369 Lock Broken!")
                    broke_369 = 1
                else:
                    broke_369 = 0
                if (np.absolute(error_399) >= max_error):
                    print("399 Lock Broken!")
                    broke_399 = 1
                else:
                    broke_399 = 0
                if (np.absolute(error_935) >= max_error):
                    print("935 Lock Broken!")
                    broke_935 = 1
                else:
                    broke_935 = 0

                # set piezo voltage
                vpc = offset_369 + GlobalGain369 * error_369
                if vpc > 69 or vpc < 0:
                    print("Piezo voltage exceed limits, v = ", vpc)
                    break
                dlcpro.laser1.dl.pc.voltage_set.set(vpc)

                # print("dv = ",GlobalGain369*error_369)

                cTime = time.mktime(
                    datetime.datetime.now().timetuple()) * 1e3 + datetime.datetime.now().microsecond / 1e3

                # To do the online tracking
                cur.execute(
                    "INSERT INTO `wavemeter`.`error` (time, `369`, `399`, `935`, 369w, 399w, 935w) VALUES (\'%s\',\'%s\',\'%s\',\'%s\',\'%s\',\'%s\',\'%s\');",
                    (cTime, round(error_369, 4), round(error_399, 4), round(error_935, 4), freq[0], freq[1], freq[2]))
                cur.execute("UPDATE `setpoint` SET `broke369`=\'%s\', `broke399`=\'%s\', `broke935`=\'%s\' WHERE 1",
                            (broke_369, broke_399, broke_935))
                con.commit()

    except DeviceNotFoundError:
        sys.stderr.write('Device not found')


if __name__ == "__main__":
    con = create_connection('127.0.0.1', 'python', 'pVW27rC1bxCR3bIj', 'wavemeter')
    cur = con.cursor()
    cur.execute("TRUNCATE TABLE `error`")
    Channels = getChannels()
    Lock()

# Todo: how to change setpoints?
