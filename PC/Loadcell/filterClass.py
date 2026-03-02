
import math
import numpy as np
import matplotlib.pyplot as plt

class Filter:

    def __init__(self):
        self.in_data = np.zeros([1])
        self.out_data = np.zeros([1])
        self.mA = np.zeros([1])
        self.mB = np.zeros([1])
        self.mA[0] = 1

    def makeFilter(self,N):
        self.N = N
        self.in_data = np.zeros([self.N + 1])
        self.out_data = np.zeros([self.N + 1])
        self.mA = np.zeros([self.N + 1])
        self.mB = np.zeros([self.N + 1])
        self.mA[0] = 1

    def Work(self,inValue):
        self.inValue = inValue
        for p in range((self.N - 1), -1, -1):
            self.in_data[p + 1] = self.in_data[p]
        for p in range((self.N - 1), -1, -1):
            self.out_data[p + 1] = self.out_data[p]
        self.in_data[0] = self.inValue
        self.out_data[0] = 0
        for p in range((self.N), -1, -1):
            self.out_data[0] += self.mB[p] * self.in_data[p]
        for p in range((self.N), 0, -1):
            self.out_data[0] -= self.mA[p] * self.out_data[p]
        return self.out_data[0]
    def print_info(self):
        print(f"In Data: {self.in_data}")
        print(f"Out Data: {self.out_data}")
        print(f"mA: {self.mA}")
        print(f"mB: {self.mB}")

class lowPass(Filter):
    def __init__(self,order,aT,aHerz):
        self.order = order
        self.aT = aT
        self.aHerz = aHerz
        self.makeFilter(self.order)
        if (self.order == 2):
            tW = 2.0 / self.aT * math.tan(self.aT * np.pi * self.aHerz)
            tG = tW * self.aT / 2
            tDenomi = 1. / (1. + math.sqrt(2.) * tG + tG * tG)
            self.mB[0] = tDenomi * tG * tG
            self.mB[1] = 2. * self.mB[0]
            self.mB[2] = self.mB[0]
            self.mA[1] = tDenomi * 2. * (tG * tG - 1)
            self.mA[2] = tDenomi * (tG * tG - math.sqrt(2.) * tG + 1)

class highPass(Filter):
    def __init__(self, order, aT, aHerz):
        self.order = order
        self.aT = aT
        self.aHerz = aHerz
        self.makeFilter(self.order)
        if (self.order == 1):
            tWH = 2.0 / aT * math.tan(self.aT * np.pi * self.aHerz)
            self.mB[0] = 2.0 / (2.0 + self.aT * tWH)
            self.mB[1] = -2.0 / (2.0 + self.aT * tWH)
            self.mA[0] = 1
            self.mA[1] = (-2.0 + self.aT * tWH) / (2.0 + self.aT * tWH)

'''
filter = lowPass(2,0.001,50)
filter.print_info()
filterH= highPass(1,0.001,100)
filterH.print_info()

t = np.linspace(-1, 1, 201)

x = (np.sin(2*np.pi*0.75*t*(1-t) + 2.1) + 0.1*np.sin(2*np.pi*1.25*t + 1) + 0.18*np.cos(2*np.pi*3.85*t))
xn = x + np.random.randn(len(t)) * 0.08
xe = xn - x
out = np.zeros([len(t)])
outH = np.zeros([len(t)])

for i in range(len(t)):
    out[i] = filter.Work(xn[i])
for l in range(len(t)):
     outH[l] = filterH.Work(xn[l])

plt.figure()
plt.plot(t,xn,'b',alpha = 0.75)
plt.plot(t,xe,'y',alpha = 0.75)
plt.plot(t,outH,'r',alpha = 0.75)
plt.show()
'''
