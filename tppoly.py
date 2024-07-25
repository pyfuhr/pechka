import os
__debug = (True if os.environ.get("DEBUG", False) else False)
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import yaml

"""
This programs return polynom which can be applied to your thermocouple
return temperature, and get fixed value of temperature

snapshotw.csv - should store header (te,t1,t2,...,t9) and data
te - temperature of reference thermocouple, t1 t2 t3 ... t9 is a temperatures
of thermocouple that need to be calibrated.
Works if your column have name "t<number>"

tp.config - yaml file contains polynomial coef which you should apply to
your tc temperature. 
"""

df= pd.read_csv('snapshotw.csv')
x = df['te']
tcn = []
for i in df.columns:
    if i[0] == 't' and i[1:].isdigit():
        tcn.append(i)

d = {i: [] for i in tcn}

for i in tcn:
    y = df[i]
    pol = np.poly1d(np.polyfit(y, x, deg=5))
    y2 = pol(y)
    d[i].extend(pol.coef.tolist())
    if __debug: 
        plt.subplot(2,1,1)
        plt.plot(x, label="x")
        plt.plot(y, label="y")
        plt.plot(y2, label="y2")
        plt.legend()
        plt.subplot(2,1,2)
        plt.plot(y2-x, label="new delta")
        plt.plot(y-x, label="old delta")
        plt.legend()
if __debug: 
    plt.show()

if __debug: print(d)

with open("tp.config", "w") as f:
    yaml.dump(d, f, default_flow_style=False)
