#BSD 2-Clause (c) 2014: A.Doherty (Oxford), D.Jackson, N.Hammerla (Newcastle)
"""
This command line application calculates average daily activity from raw
accelerometer data as follows:
    1) Extract and filter sum vector magnitude values for <60>sec epochs
    2) Identify nonWear data in the epochs, and remove it
    3) Construct an avg movement value for each of 1440 minutes in an avg day
    4) Get overall average movement per second from step 3
=== === === ===
The application can be run as follows:
    python ActivitySummary.py <input_file.CWA> <options>
e.g.
    python ActivitySummary.py p001.CWA 
    python ActivitySummary.py p001.CWA min_freq:10 
"""

import collections
import datetime
import json
import os
import pandas as pd
import numpy as np
import statsmodels.api as sm
from subprocess import call, Popen
import struct
import sys

def main():
    """
    Application entry point responsible for parsing command line requests
    """
    print sys.argv
    #check that enough command line arguments are entered
    if len(sys.argv)<2:
        msg = "\n Invalid input, please enter at least 1 parameter, e.g."
        msg += "\n python ActivitySummary.py inputFile.CWA \n"
        print msg
        sys.exit(0)
    #store command line arguments to local variables
    rawFile = sys.argv[1]      
    funcParams = sys.argv[2:]
    rawFileEnd = '.' + rawFile.split('.')[-1]
    summaryFile = rawFile.replace(rawFileEnd, "OutputSummary.json")
    tsFile = rawFile.replace(rawFileEnd,"AccTimeSeries.csv")
    nonWearFile = rawFile.replace(rawFileEnd,"NonWearBouts.csv")
    epochFile = rawFile.replace(rawFileEnd,"Epoch.csv")
    stationaryFile = rawFile.replace(rawFileEnd,"Stationary.csv")
    javaEpochProcess = "AxivityAx3Epochs"
    javaHeapSpace = ""
    skipRaw = False
    skipCalibration = False
    deleteHelperFiles = True
    verbose = False
    epochPeriod = 5
    calOff = [0.0, 0.0, 0.0]
    calSlope = [1.0, 1.0, 1.0]
    calTemp = [0.0, 0.0, 0.0]
    meanTemp = 20
    #update default values by looping through user parameters
    for param in funcParams:
        #example param -> 'matlab:/Applications/MATLAB_R2014a.app/bin/matlab'
        if param.split(':')[0] == 'summaryFolder':
            summaryFile = param.split(':')[1] + summaryFile.split('/')[-1]
        elif param.split(':')[0] == 'epochFolder':
            epochFile = param.split(':')[1] + epochFile.split('/')[-1]
        elif param.split(':')[0] == 'nonWearFolder':
            nonWearFile = param.split(':')[1] + nonWearFile.split('/')[-1]
        elif param.split(':')[0] == 'stationaryFolder':
            stationaryFile = param.split(':')[1] + stationaryFile.split('/')[-1]
        elif param.split(':')[0] == 'timeSeriesFolder':
            tsFile = param.split(':')[1] + tsFile.split('/')[-1]
        elif param.split(':')[0] == 'skipRaw':
            skipRaw = param.split(':')[1] in ['true', 'True']
        elif param.split(':')[0] == 'skipCalibration':
            skipCalibration = param.split(':')[1] in ['true', 'True']
        elif param.split(':')[0] == 'verbose':
            verbose = param.split(':')[1] in ['true', 'True']
        elif param.split(':')[0] == 'deleteHelperFiles':
            deleteHelperFiles = param.split(':')[1] in ['true', 'True']
        elif param.split(':')[0] == 'epochPeriod':
            epochPeriod = int(float(param.split(':')[1]))
        elif ( param.split(':')[0] == 'javaHeapSpace' and
                len(param.split(':')[1])>1 ):
            javaHeapSpace = param.split(':')[1]
        elif ( param.split(':')[0] == 'javaEpochProcess' and
                len(param.split(':')[1])>1 ):
            javaEpochProcess = param.split(':')[1]
        elif ( param.split(':')[0] == 'calOff' and
                len(param.split(':')[1].split(','))==3 ):
            calOff = param.split(':')[1].split(',')
            skipCalibration = True
        elif ( param.split(':')[0] == 'calSlope' and 
                len(param.split(':')[1].split(','))==3 ):
            calSlope = param.split(':')[1].split(',')
            skipCalibration = True
        elif ( param.split(':')[0] == 'calTemp' and 
                len(param.split(':')[1].split(','))==3 ):
            calTemp = param.split(':')[1].split(',')
            skipCalibration = True
        elif ( param.split(':')[0] == 'calMeanTemp' and 
                len(param.split(':')[1])>=1 ):
            meanTemp = param.split(':')[1]
            skipCalibration = True

    #check source cwa file exists
    if not skipRaw and not os.path.isfile(rawFile):
        msg = "\n Invalid input"
        msg += "\n File does not exist: " + rawFile + "\n"
        sys.stderr.write(toScreen(msg))
        sys.exit(0)

    if not skipRaw:
        #calibrate axes scale/offset values
        if not skipCalibration:
            #identify 10sec stationary epochs
            print toScreen('calibrating')
            commandArgs = ["java", "-cp", ".", "-XX:ParallelGCThreads=1",
                    javaEpochProcess, rawFile, "outputFile:" + stationaryFile,
                    "verbose:" + str(verbose), "filter:true",
                    "getStationaryBouts:true", "epochPeriod:10",
                    "stationaryStd:0.013"]
            if len(javaHeapSpace) > 1:
                commandArgs.insert(1,javaHeapSpace);
            call(commandArgs)
            #record calibrated axes scale/offset/temperature vals + static point stats
            calOff, calSlope, calTemp, meanTemp, errPreCal, errPostCal, xMin, \
                    xMax, yMin, yMax, zMin, zMax, \
                    nStatic = getCalibrationCoefs(stationaryFile)
            if verbose:
                print calOff, calSlope, calTemp, meanTemp, errPreCal, \
                        errPostCal, xMin, xMax, yMin, yMax, zMin, zMax, nStatic
      
        #calculate and write filtered avgVm epochs from raw file
        commandArgs = ["java", "-cp", ".", "-XX:ParallelGCThreads=1",
                javaEpochProcess, rawFile, "outputFile:" + epochFile,
                "verbose:" + str(verbose), "filter:true",
                "xIntercept:" + str(calOff[0]), "yIntercept:" + str(calOff[1]),
                "zIntercept:" + str(calOff[2]), "xSlope:" + str(calSlope[0]),
                "ySlope:" + str(calSlope[1]), "zSlope:" + str(calSlope[2]),
                "xTemp:" + str(calTemp[0]), "yTemp:" + str(calTemp[1]),
                "zTemp:" + str(calTemp[2]), "meanTemp:" + str(meanTemp),
                "epochPeriod:" + str(epochPeriod)]
        print toScreen('epoch generation')
        if len(javaHeapSpace) > 1:
            commandArgs.insert(1,javaHeapSpace);
        call(commandArgs)
    
    #calculate average, median, stdev, min, max, count, & ecdf of sample score in
    #1440 min diurnally adjusted day. Also get overall wear time minutes across
    #each hour
    print toScreen('generate summary variables from epochs')
    startTime, endTime, wearTimeMins, nonWearTimeMins, numNonWearEpisodes, \
            wearDay, wear24, diurnalHrs, diurnalMins, numInterrupts, \
            interruptMins, numDataErrs, clipsPreCalibrSum, clipsPreCalibrMax, \
            clipsPostCalibrSum, clipsPostCalibrMax, epochSamplesN, \
            epochSamplesAvg, epochSamplesStd, epochSamplesMin, epochSamplesMax, \
            tempMean, tempStd, tempMin, tempMax, paWAvg, paWStd, paAvg, paStd, \
            paMedian, paMin, paMax, paDays, paHours, paEcdf1, paEcdf2, paEcdf3, \
            paEcdf4 = getEpochSummary(epochFile, 0, 0, epochPeriod, 
                    nonWearFile, tsFile)
    
    #data integrity outputs
    maxErrorRate = 0.001
    lowErrorRate = 1
    norm = epochSamplesN*1.0
    if ( clipsPreCalibrSum/norm >= maxErrorRate or 
            clipsPostCalibrSum/norm >= maxErrorRate or 
            numDataErrs/norm >= maxErrorRate ):
        lowErrorRate = 0
    #min wear time
    minDiurnalHrs = 24
    minWearDays = 5
    goodWearTime = 1
    if diurnalHrs < minDiurnalHrs or wearTimeMins/1440.0 < minWearDays:
        goodWearTime = 0
    #good calibration
    goodCalibration = 1
    s = 0.3 #sphere criteria
    if xMin>-s or xMax<s or yMin>-s or yMax<s or zMin>-s or zMax<s or \
            np.isnan(xMin) or np.isnan(yMin) or np.isnan(zMin):
        goodCalibration = 0
    #calibrated on own data
    calibratedOnOwnData = 1
    if skipCalibration:
        calibratedOnOwnData = 0
    
    #store variables to dictionary
    result = collections.OrderedDict()
    result['file-name'] = rawFile
    f = '%Y-%m-%d %H:%M:%S'
    result['file-startTime'] = startTime.strftime(f)
    result['file-endTime'] = endTime.strftime(f)
    #physical activity output variable (mg)
    result['acc-overall-avg(mg)'] = formatNum(paWAvg*1000, 2)
    result['acc-overall-std(mg)'] = formatNum(paWStd*1000, 2)
    #data integrity outputs
    result['quality-lowErrorRate'] = lowErrorRate
    result['quality-goodWearTime'] = goodWearTime
    result['quality-goodCalibration'] = goodCalibration
    result['quality-calibratedOnOwnData'] = calibratedOnOwnData
    #physical activity variation by day / hour
    result['acc-mon-avg(mg)'] = formatNum(paDays[0]*1000, 2)
    result['acc-tue-avg(mg)'] = formatNum(paDays[1]*1000, 2)
    result['acc-wed-avg(mg)'] = formatNum(paDays[2]*1000, 2)
    result['acc-thur-avg(mg)'] = formatNum(paDays[3]*1000, 2)
    result['acc-fri-avg(mg)'] = formatNum(paDays[4]*1000, 2)
    result['acc-sat-avg(mg)'] = formatNum(paDays[5]*1000, 2)
    result['acc-sun-avg(mg)'] = formatNum(paDays[6]*1000, 2)
    result['file-firstDay(0=mon,6=sun)'] = startTime.weekday()
    for i in range(0,24):
        result['acc-hourOfDay' + str(i) + '-avg(mg)'] = formatNum(paHours[i]*1000, 2)
    #wear time characteristics
    result['wearTime-overall(days)'] = formatNum(wearTimeMins/1440.0, 2)
    result['nonWearTime-overall(days)'] = formatNum(nonWearTimeMins/1440.0, 2)
    result['wearTime-mon(hrs)'] = formatNum(wearDay[0]/60.0, 2)
    result['wearTime-tue(hrs)'] = formatNum(wearDay[1]/60.0, 2)
    result['wearTime-wed(hrs)'] = formatNum(wearDay[2]/60.0, 2)
    result['wearTime-thur(hrs)'] = formatNum(wearDay[3]/60.0, 2)
    result['wearTime-fri(hrs)'] = formatNum(wearDay[4]/60.0, 2)
    result['wearTime-sat(hrs)'] = formatNum(wearDay[5]/60.0, 2)
    result['wearTime-sun(hrs)'] = formatNum(wearDay[6]/60.0, 2)
    for i in range(0,24):
        result['wearTime-hourOfDay' + str(i) + '-(hrs)'] = formatNum(wear24[i]/60.0, 2)
    result['wearTime-diurnalHrs'] = diurnalHrs
    result['wearTime-diurnalMins'] = diurnalMins
    try:
        result['wearTime-numNonWearEpisodes(>1hr)'] = numNonWearEpisodes
    except:
        result['wearTime-numNonWearEpisodes(>1hr)'] = -1
    #physical activity stats and intensity distribution (minus diurnalWeights)
    result['acc-noDiurnalAdjust-avg(mg)'] = formatNum(paAvg*1000, 2)
    result['acc-noDiurnalAdjust-std(mg)'] = formatNum(paStd*1000, 2)
    result['acc-noDiurnalAdjust-median(mg)'] = formatNum(paMedian*1000, 2)
    result['acc-noDiurnalAdjust-min(mg)'] = formatNum(paMin*1000, 2)
    result['acc-noDiurnalAdjust-max(mg)'] = formatNum(paMax*1000, 2)
    for i in range(1,21): #1mg categories from 1-20mg
        result['acc-ecdf-' + str(i) + 'mg'] = formatNum(paEcdf1[i-1], 3)
    for i in range(1,17): #5mg categories from 25-100mg
        result['acc-ecdf-' + str(20+i*5) + 'mg'] = formatNum(paEcdf2[i-1], 3)
    for i in range(1,17): #25mg categories from 125-500mg
        result['acc-ecdf-' + str(100+i*25) + 'mg'] = formatNum(paEcdf3[i-1], 3)
    for i in range(1,16): #100mg categories from 500-2000mg
        result['acc-ecdf-' + str(500+i*100) + 'mg'] = formatNum(paEcdf4[i-1], 3)
    
    try:
        #calibration metrics 
        result['calibration-errsBefore'] = errPreCal
        result['calibration-errsAfter'] = errPostCal
        result['calibration-xOffset'] = calOff[0]
        result['calibration-yOffset'] = calOff[1]
        result['calibration-zOffset'] = calOff[2]
        result['calibration-xSlope'] = calSlope[0]
        result['calibration-ySlope'] = calSlope[1]
        result['calibration-zSlope'] = calSlope[2]
        result['calibration-xTemp'] = calTemp[0]
        result['calibration-yTemp'] = calTemp[1]
        result['calibration-zTemp'] = calTemp[2]
        result['calibration-meanDeviceTemp'] = meanTemp
        result['calibration-numStaticPoints'] = nStatic
        result['calibration-staticXmin'] = formatNum(xMin, 2)
        result['calibration-staticXmax'] = formatNum(xMax, 2)
        result['calibration-staticYmin'] = formatNum(yMin, 2)
        result['calibration-staticYmax'] = formatNum(yMax, 2)
        result['calibration-staticZmin'] = formatNum(zMin, 2)
        result['calibration-staticZmax'] = formatNum(zMax, 2)
    except:
        result['calibration-errsBefore'] = -1
        result['calibration-errsAfter'] = -1
        result['calibration-xOffset'] = -1
        result['calibration-yOffset'] = -1
        result['calibration-zOffset'] = -1
        result['calibration-xSlope'] = -1
        result['calibration-ySlope'] = -1
        result['calibration-zSlope'] = -1
        result['calibration-xTemp'] = -1
        result['calibration-yTemp'] = -1
        result['calibration-zTemp'] = -1
        result['calibration-meanDeviceTemp'] = -1
        result['calibration-numStaticPoints'] = -1
        result['calibration-staticXmin'] = -1
        result['calibration-staticXmax'] = -1
        result['calibration-staticYmin'] = -1
        result['calibration-staticYmax'] = -1
        result['calibration-staticZmin'] = -1
        result['calibration-staticZmax'] = -1
    try:
        #raw file data quality indicators
        result['file-size'] = os.path.getsize(rawFile)
        result['file-deviceID'] = getDeviceId(rawFile)
    except:
        result['file-size'] = -1
        result['file-deviceID'] = -1
    #other housekeeping variables
    result['errs-interrupts-num'] = numInterrupts
    result['errs-interrupt-mins'] = formatNum(interruptMins, 1)
    result['errs-data-num'] = numDataErrs
    result['clips-beforeCalibration-num'] = clipsPreCalibrSum
    result['clips-beforeCalibration-max(perEpoch)'] = clipsPreCalibrMax
    result['clips-afterCalibration-num'] = clipsPostCalibrSum
    result['clips-afterCalibration-max(perEpoch)'] = clipsPostCalibrMax
    result['totalSamples'] = epochSamplesN
    result['sampleRate-avg(Hz)'] = formatNum(epochSamplesAvg / epochPeriod, 1)
    result['sampleRate-std(Hz)'] = formatNum(epochSamplesStd / epochPeriod, 1)
    result['sampleRate-min(Hz)'] = formatNum(epochSamplesMin / epochPeriod, 1)
    result['sampleRate-max(Hz)'] = formatNum(epochSamplesMax / epochPeriod, 1)
    result['deviceTemp-mean'] = formatNum(tempMean, 1)
    result['deviceTemp-std'] = formatNum(tempStd, 1)
    result['deviceTemp-min'] = formatNum(tempMin, 1)
    result['deviceTemp-max'] = formatNum(tempMax, 1)
    
    #print basic output
    summaryVals = ['file-name', 'file-startTime', 'file-endTime', 'acc-overall-avg(mg)','wearTime-overall(days)','nonWearTime-overall(days)']
    summaryDict = collections.OrderedDict([(i, result[i]) for i in summaryVals])
    print toScreen(json.dumps(summaryDict, indent=4))
    
    #write detailed output to file
    f = open(summaryFile,'w')
    json.dump(result, f, indent=4)
    f.close()
    if deleteHelperFiles:
        try:
            os.remove(stationaryFile)
            os.remove(epochFile)
        except:
            print 'could not delete helper file' 
    if verbose:
        print toScreen('see all variables at: ' + summaryFile)


def getEpochSummary(epochFile,
        headerSize,
        dateColumn,
        epochSec,
        nonWearFile,
        tsFile):
    """
    Calculate diurnally adjusted average movement per minute from epoch file
    which has had nonWear episodes removed from it
    """
    #use python PANDAS framework to read in and store epochs
    e = pd.read_csv(epochFile, index_col=dateColumn, parse_dates=True,
                header=headerSize).sort_index()
    #get start & end times, plus wear & nonWear minutes
    startTime = pd.to_datetime(e.index.values[0])
    endTime = pd.to_datetime(e.index.values[-1])

    #calculate nonWear (nw) time
    minDuration = 60 #minutes
    maxStd = 0.013
    e['nw'] = np.where((e['xStd']<maxStd) & (e['yStd']<maxStd) & 
            (e['zStd']<maxStd),1,0)
    starts = e.index[(e['nw']==True) & (e['nw'].shift(1).fillna(False)==False)]
    ends = e.index[(e['nw']==True) & (e['nw'].shift(-1).fillna(False)==False)]
    nonWearEpisodes = [(start, end) for start, end in zip(starts, ends)
            if end > start + np.timedelta64(minDuration,'m')]
    #set nonWear data to nan and record to nonWearBouts file
    f = open(nonWearFile,'w')
    f.write('start,end,xStdMax,yStdMax,zStdMax\n')
    timeFormat = '%Y-%m-%d %H:%M:%S'
    for episode in nonWearEpisodes:
        tmp = e[['xStd','yStd','zStd']][episode[0]:episode[1]]
        summary = episode[0].strftime(timeFormat) + ','
        summary += episode[1].strftime(timeFormat) + ','
        summary += str(tmp['xStd'].mean()) + ','
        summary += str(tmp['yStd'].mean()) + ','
        summary += str(tmp['zStd'].mean())
        f.write(summary + '\n')
        #set main dataframe values to nan
        e[episode[0]:episode[1]] = np.nan
    f.close()

    paCol = 'enmoTrunc'
    wearSamples = e[paCol].count()
    nonWearSamples = len(e[np.isnan(e[paCol])].index.values)
    wearTimeMin = wearSamples * epochSec / 60.0
    nonWearTimeMin = nonWearSamples * epochSec / 60.0
   
    #get wear time in each of 24 hours across week
    epochsInMin = 60 / epochSec
    wearDay = []
    for i in range(0,7):
        wearDay.append( e[paCol][e.index.weekday == i].count() / epochsInMin )
    wear24 = []
    for i in range(0,24):
        wear24.append( e[paCol][e.index.hour == i].count() / epochsInMin )
    diurnalHrs = e[paCol].groupby(e.index.hour).mean().count()
    diurnalMins = e[paCol].groupby([e.index.hour,e.index.minute]).mean().count()

    #calculate imputation values to replace nan PA metric values
    #i.e. replace with mean avgVm from same time in other days
    e['hour'] = e.index.hour
    e['minute'] = e.index.minute
    wearTimeWeights = e.groupby(['hour', 'minute'])[paCol].mean() #weartime weighted data
    e = e.join(wearTimeWeights, on=['hour','minute'], rsuffix='_imputed')
    
    pa = e[paCol] #raw data
    #calculate stat summaries
    paAvg = pa.mean()
    paStd = pa.std()
    paMedian = pa.median()
    paMin = pa.min()
    paMax = pa.max()
    
    #now wearTime weight values
    e[paCol+'Adjusted'] = e[paCol].fillna(e[paCol + '_imputed'])
    pa = e[paCol+'Adjusted'] #weartime weighted data
    paWAvg = pa.mean()
    paWStd = pa.std()
    paDays = []
    for i in range(0,7):
        paDays.append(pa[pa.index.weekday == i].mean())
    paHours = []
    for i in range(0,24):
        paHours.append(pa[pa.index.hour == i].mean())

    #calculate empirical cumulative distribution function of vector magnitudes
    pa = pa[~np.isnan(pa)] #remove NaNs (necessary for statsmodels.api)
    if len(pa) > 0:
        ecdf = sm.distributions.ECDF(pa)
        x, step = np.linspace(0.001, 0.020, 20, retstep=True) #1mg bins from 1-20mg
        paEcdf1 = ecdf(x)
        x, step = np.linspace(0.025, 0.100, 16, retstep=True) #5mg bins from 25-100mg
        paEcdf2 = ecdf(x)
        x, step = np.linspace(0.125, 0.500, 16, retstep=True) #25mg bins from 125-500mg
        paEcdf3 = ecdf(x)
        x, step = np.linspace(0.6, 2.0, 15, retstep=True) #100mg bins from 500-2000mg
        paEcdf4 = ecdf(x)
    else:
        paEcdf1 = np.empty(20)
        paEcdf2 = np.empty(16)
        paEcdf3 = np.empty(16)
        paEcdf4 = np.empty(15)
    
    #prepare time series header
    tsHead = 'acceleration (mg) - '
    tsHead += e.index.min().strftime('%Y-%m-%d %H:%M:%S') + ' - '
    tsHead += e.index.max().strftime('%Y-%m-%d %H:%M:%S') + ' - '
    tsHead += 'sampleRate = ' + str(epochSec) + ' seconds'
    if len(pa) > 0:
        #write time series file
        #convert 'vm' to mg units, and highlight any imputed values
        e['vmFinal'] = e[paCol+'Adjusted'] * 1000
        e['imputed'] = np.isnan(e[paCol]).replace({True:'1',False:''})
        e[['vmFinal','imputed']].to_csv(tsFile, float_format='%.1f',
                index=False,header=[tsHead,'imputed'])
    else:
        f = open(tsFile,'w')
        f.write(tsHead + '\n')
        f.write('no wearTime data,1')
        f.close()
   
    #get interrupt and data error summary vals
    epochNs = epochSec * np.timedelta64(1,'s')
    interrupts = np.where(np.diff(np.array(e.index)) > epochNs)[0]
    #get duration of each interrupt in minutes
    interruptMins = []
    for i in interrupts:
        interruptMins.append( np.diff(np.array(e[i:i+2].index)) /
                np.timedelta64(1,'m') )

    #return physical activity summary
    return startTime, endTime, wearTimeMin, nonWearTimeMin, \
            len(nonWearEpisodes), wearDay, wear24, diurnalHrs, diurnalMins, \
            len(interrupts), np.sum(interruptMins), e['dataErrors'].sum(), \
            e['clipsBeforeCalibr'].sum(), e['clipsBeforeCalibr'].max(), \
            e['clipsAfterCalibr'].sum(), e['clipsAfterCalibr'].max(), \
            e['samples'].sum(), e['samples'].mean(), e['samples'].std(), \
            e['samples'].min(), e['samples'].max(), e['temp'].mean(), \
            e['temp'].std(), e['temp'].min(), e['temp'].max(), paWAvg, paWStd, \
            paAvg, paStd, paMedian, paMin, paMax, paDays, paHours, paEcdf1, \
            paEcdf2, paEcdf3, paEcdf4


def getCalibrationCoefs(staticBoutsFile):
    """
    Get axes offset/gain/temp calibration coefficients through linear regression
    of stationary episodes
    """
    #learning/research parameters
    maxIter = 1000
    minIterImprovement = 0.0001 #0.1mg
    #use python NUMPY framework to store stationary episodes from epoch file
    d = np.loadtxt(open(staticBoutsFile,"rb"),delimiter=",",skiprows=1,
            usecols=(2,3,4,11,13))
    if len(d)<=5: 
        return [0.0,0.0,0.0], [1.0,1.0,1.0], [0.0,0.0,0.0], 20, np.nan, np.nan, \
            np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, len(d) 
    stationaryPoints = d[d[:,4] == 0] #don't consider episodes with data errors
    axesVals = stationaryPoints[:,[0,1,2]]
    tempVals = stationaryPoints[:,[3]]
    meanTemp = np.mean(tempVals)
    tempVals = np.copy(tempVals-meanTemp)
    #store information on spread of stationary points
    xMin, yMin, zMin = np.amin(axesVals, axis=0)
    xMax, yMax, zMax = np.amax(axesVals, axis=0)
    #initialise intercept/slope variables to assume no error initially present
    intercept = np.array([0.0, 0.0, 0.0])
    slope = np.array([1.0, 1.0, 1.0])
    tempCoef = np.array([0.0, 0.0, 0.0])
    #variables to support model fitting
    initError = float("inf")
    prevError = float("inf")
    bestError = float("inf")
    bestIntercept = np.copy(intercept)
    bestSlope = np.copy(slope)
    bestTemp = np.copy(tempCoef)
    #record initial uncalibrated error
    curr = intercept + (np.copy(axesVals) * slope) + (np.copy(tempVals) * tempCoef)
    target = curr / np.sqrt(np.sum(np.square(curr), axis=1))[:,None]
    initError = np.sqrt(np.mean(np.square(curr-target))) #root mean square error
    #iterate through linear model fitting
    try:
        for i in range(1, maxIter):
            #iterate through each axis, refitting its intercept/slope vals
            for a in range(0,3):
                x = np.concatenate([curr[:,[a]], tempVals], axis=1)
                x = sm.add_constant(x, prepend=True) #add bias/intercept term
                y = target[:,a]
                newI, newS, newT = sm.OLS(y,x).fit().params
                #update values as part of iterative closest point fitting process
                #refer to wiki as there is quite a bit of math behind next 3 lines
                intercept[a] = newI + (intercept[a] * newS)
                slope[a] = newS * slope[a]
                tempCoef[a] = newT + (tempCoef[a] * newS)
            #update vals (and targed) based on new intercept/slope/temp coeffs
            curr = intercept + (np.copy(axesVals) * slope) + (np.copy(tempVals) * tempCoef)
            target = curr / np.sqrt(np.sum(np.square(curr), axis=1))[:,None]
            rms = np.sqrt(np.mean(np.square(curr-target))) #root mean square error
            #assess iterative error convergence
            improvement = (bestError-rms)/bestError
            prevError=rms
            if rms < bestError:
                bestIntercept = np.copy(intercept)
                bestSlope = np.copy(slope)
                bestTemp = np.copy(tempCoef)
                bestError = rms
            if improvement < minIterImprovement:
                break #break if not largely converged
    except:
        #highlight problem with regression, and exit
        xMin, yMin, zMin = float('nan'), float('nan'), float('nan')
        xMax, yMax, zMax = float('nan'), float('nan'), float('nan')
        sys.stderr.write('WARNING: calibration error\n')
    return bestIntercept, bestSlope, bestTemp, meanTemp, initError, bestError, \
            xMin, xMax, yMin, yMax, zMin, zMax, len(axesVals)


def getDeviceId(cwaFile):
    f = open(cwaFile, 'rb')
    header = f.read(2)
    if header == 'MD':
        blockSize = struct.unpack('H', f.read(2))[0]
        performClear = struct.unpack('B', f.read(1))[0]
        deviceId = struct.unpack('H', f.read(2))[0]
    f.close()
    return deviceId

def formatNum(num, decimalPlaces):
    fmt = '%.' + str(decimalPlaces) + 'f'
    return float(fmt % num)

def toScreen(msg):
    timeFormat = '%Y-%m-%d %H:%M:%S'
    return datetime.datetime.now().strftime(timeFormat) +  ' ' + msg

"""
Standard boilerplate to call the main() function to begin the program.
"""
if __name__ == '__main__': 
    main() #Standard boilerplate to call the main() function to begin the program.
