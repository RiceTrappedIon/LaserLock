import nidaqmx

with nidaqmx.Task() as task:
    task.ao_channels.add_ao_voltage_chan("Dev2/ao0")
    task.write(11)
