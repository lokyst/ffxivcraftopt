# This file is part of the FFXIV CraftOptimizer
# by Rhoda Baker (rhoda.baker@gmail.com)
#
# TODO
# Initial guess for GP method
# HQ function
# UI

from __future__ import print_function
import random, math, sys
from functools import partial

from deap import algorithms
from deap import base
from deap import creator
from deap import tools
from deap import gp

# ==== Logging

class Logger(object):
    def __init__(self, out):
        if out is None:
            out = sys.stdout
        self.out = out

    def log(self, s):
        self.out.write(s)
        self.out.write("\n")

# ==== GP AST functions
def progn(*args):
    for arg in args:
        arg()

def prog2(out1, out2):
    return partial(progn,out1,out2)

def flatten_prog(prog):
    return [x.value for x in prog if isinstance(x, gp.Terminal)]

# ==== Macro Stuff
def CreateMacro(actionList, waitTime=3, insertTricks=False):
    macroList = [x.name for x in actionList if x != dummyAction and x != tricksOfTheTrade]        # Strip dummy actions and tricks

    maxLines = 14

    macroStringList = []
    waitString = "/wait %i\n" % (waitTime,)
    for action in macroList:
        macroStringList.append("/ac \"" + action + "\" <me>\n")
        macroStringList.append(waitString)
        if insertTricks:
            macroStringList.append("/ac \"" + tricksOfTheTrade.name + "\" <me>\n")
            macroStringList.append(waitString)

    macroString = ""
    count = 0
    for actionString in macroStringList:
        count += 1
        macroString += actionString
        if count % maxLines == 0:
            macroString += "/echo Macro step %i complete" % (count/maxLines,)
            macroString += "\n=====================================\n\n"
    macroString += "/echo Macro step %i complete" % (math.ceil(count/maxLines),)

    return macroString

# ==== Model Stuff
class Crafter:
    def __init__(self, level=0, craftsmanship=0, control=0, craftPoints=0, actions=None):
        self.craftsmanship = craftsmanship
        self.control = control
        self.craftPoints = craftPoints
        self.level = level
        if actions is None:
            self.actions = []
        else:
            self.actions = actions

class Recipe:
    def __init__(self, level=0, difficulty=0, durability=0, startQuality= 0, maxQuality=0):
        self.level = level
        self.difficulty = difficulty
        self.durability = durability
        self.startQuality = startQuality
        self.maxQuality = maxQuality

#noinspection PyMethodMayBeStatic
class Synth:
    def __init__(self, crafter, recipe, maxTrickUses=0, useConditions=False):
        self.crafter = crafter
        self.recipe = recipe
        self.maxTrickUses = maxTrickUses
        self.useConditions = useConditions

    def CalculateBaseProgressIncrease(self, levelDifference, craftsmanship):
        if -5 <= levelDifference <= 0:
            levelCorrectionFactor = 0.10 * levelDifference
        elif 0 < levelDifference <= 5:
            levelCorrectionFactor = 0.05 * levelDifference
        elif 5 < levelDifference <= 15:
            levelCorrectionFactor = 0.022 * levelDifference + 0.15
        else:
            levelCorrectionFactor = 0.022 * levelDifference + 0.15
        # Failed data points
        # Ldiff, Craftsmanship, Actual Progress, Expected Progress
        # 15, 136, 44, 45

        baseProgress = 0.21 * craftsmanship + 1.6
        levelCorrectedProgress = baseProgress * (1 + levelCorrectionFactor)

        return round(levelCorrectedProgress, 0)

    def CalculateBaseQualityIncrease(self, levelDifference, control):
        if -5 <= levelDifference <= 0:
            levelCorrectionFactor = 0.05 * levelDifference
        else:
            levelCorrectionFactor = 0

        baseQuality = 0.36 * control + 34
        levelCorrectedQuality = baseQuality * (1 + levelCorrectionFactor)

        return round(levelCorrectedQuality, 0)

class Action:
    def __init__(self, shortName, name, durabilityCost=0, cpCost=0, successProbability=1.0, qualityIncreaseMultiplier=0.0, progressIncreaseMultiplier=0.0, aType='immediate', activeTurns=1):
        self.shortName = shortName
        self.name = name
        self.durabilityCost = durabilityCost
        self.cpCost = cpCost
        self.successProbability = successProbability
        self.qualityIncreaseMultiplier = qualityIncreaseMultiplier
        self.progressIncreaseMultiplier = progressIncreaseMultiplier
        self.type = aType
        if aType != "immediate":
            self.activeTurns = activeTurns      # Save some space

    def __eq__(self, other):
        if self.name == other.name:
            return True
        else:
            return False

    def __ne__(self, other):
        if self.name != other.name:
            return True
        else:
            return False

    def __repr__(self):
        return self.shortName

    def __str__(self):
        return self.shortName

class EffectTracker:
    def __init__(self):
        self.countUps = {}
        self.countDowns = {}
        self.toggles = {}

class State:
    def __init__(self, step=0, action="", durabilityState=0, cpState=0, qualityState=0, progressState=0, wastedActions=0, progressOk=False, cpOk=False, durabilityOk=False, trickOk=False):
        self.step = step
        self.action = action
        self.durabilityState = durabilityState
        self.cpState = cpState
        self.qualityState = qualityState
        self.progressState = progressState
        self.wastedActions = wastedActions
        self.progressOk = progressOk
        self.cpOk = cpOk
        self.durabilityOk = durabilityOk
        self.trickOk = trickOk

# Probabalistic Simulation Function
def simSynth(individual, synth, verbose=True, debug=False, logOutput=None):
    logger = Logger(logOutput)
    
    # State tracking
    durabilityState = synth.recipe.durability
    cpState = synth.crafter.craftPoints
    progressState = 0
    qualityState = synth.recipe.startQuality
    stepCount = 0
    wastedActions = 0
    effects = EffectTracker()
    trickUses = 0

    # Conditions
    pGood = 0.23
    pExcellent = 0.01
    pPoor = pExcellent

    # Step 1 is always normal
    ppGood = 0
    ppExcellent = 0
    ppPoor = 0
    ppNormal = 1 - (pGood + pExcellent + pPoor)

    # End state checks
    progressOk = False
    cpOk = False
    durabilityOk = False
    trickOk = False

    if verbose:
        logger.log("%2s %-20s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC"))
        logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions))

    if debug:
        logger.log("%2s %-20s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC", "IQ", "CTL", "QINC", "BPRG", "BQUA"))
        logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions, 0, synth.crafter.control, 0))

    for action in individual:
        # Occur regardless of dummy actions
        #==================================
        stepCount += 1

        # Add effect modifiers
        craftsmanship = synth.crafter.craftsmanship
        control = synth.crafter.control
        if innerQuiet.name in effects.countUps:
            control *= (1 + 0.2 * effects.countUps[innerQuiet.name])

        if innovation.name in effects.countDowns:
            control *= 1.5

        levelDifference = synth.crafter.level - synth.recipe.level
        if ingenuity2.name in effects.countDowns:
            levelDifference = 3
        elif ingenuity.name in effects.countDowns:
            levelDifference = 0

        if steadyHand2.name in effects.countDowns:
            successProbability = action.successProbability + 0.3        # What is effect of having both active? Assume 2 always overrides 1 but does not overwrite
        elif steadyHand.name in effects.countDowns:
            successProbability = action.successProbability + 0.2
        else:
            successProbability = action.successProbability
        successProbability = min(successProbability, 1)

        qualityIncreaseMultiplier = action.qualityIncreaseMultiplier
        if greatStrides.name in effects.countDowns:
            qualityIncreaseMultiplier *= 2

        # Condition Calculation
        if synth.useConditions:
            qualityIncreaseMultiplier *= (1*ppNormal + 1.5*ppGood + 4*ppExcellent + 0.5*ppPoor)

        # Calculate final gains / losses
        bProgressGain = action.progressIncreaseMultiplier * synth.CalculateBaseProgressIncrease(levelDifference, craftsmanship)
        if action == flawlessSynthesis:
            bProgressGain = 40
        elif action == pieceByPiece:
            bProgressGain = (synth.recipe.difficulty - progressState)/3
        progressGain = successProbability * bProgressGain

        bQualityGain = qualityIncreaseMultiplier * synth.CalculateBaseQualityIncrease(levelDifference, control)
        qualityGain = successProbability * bQualityGain
        if action == byregotsBlessing:
            qualityGain *= (1 + 0.2 * effects.countUps[innerQuiet.name])

        durabilityCost = action.durabilityCost
        if wasteNot.name in effects.countDowns or wasteNot2.name in effects.countDowns:
            durabilityCost = 0.5 * action.durabilityCost

        # Occur if a dummy action
        #==================================
        if (progressState >= synth.recipe.difficulty or durabilityState <= 0) and action != dummyAction:
            wastedActions += 1

        # Occur if not a dummy action
        #==================================
        else:
            # State tracking
            progressState += progressGain
            qualityState += qualityGain
            durabilityState -= durabilityCost
            cpState -= action.cpCost

            # Effect management
            #==================================
            # Special Effect Actions
            if action == mastersMend:
                durabilityState += 30

            if action == mastersMend2:
                durabilityState += 60

            if manipulation.name in effects.countDowns and durabilityState > 0:
                durabilityState += 10

            if comfortZone.name in effects.countDowns and cpState > 0:
                cpState += 8

            if action == rumination and cpState > 0:
                if innerQuiet.name in effects.countUps and effects.countUps[innerQuiet.name] > 0:
                    cpState += (21 * effects.countUps[innerQuiet.name] - effects.countUps[innerQuiet.name]**2 + 10)/2
                    del effects.countUps[innerQuiet.name]
                else:
                    wastedActions += 1

            if action == byregotsBlessing:
                if innerQuiet.name in effects.countUps:
                    del effects.countUps[innerQuiet.name]
                else:
                    wastedActions += 1

            if action.qualityIncreaseMultiplier > 0 and greatStrides.name in effects.countDowns:
                del effects.countDowns[greatStrides.name]

            if action == tricksOfTheTrade and cpState > 0:
                trickUses += 1
                cpState += 20

            # Conditions
            if synth.useConditions:
                ppPoor = ppExcellent
                ppGood = pGood * ppNormal
                ppExcellent = pExcellent * ppNormal
                ppNormal = 1 - (ppGood + ppExcellent + ppPoor)

            # Decrement countdowns
            for countDown in list(effects.countDowns.keys()):
                effects.countDowns[countDown] -= 1
                if effects.countDowns[countDown] == 0:
                    del effects.countDowns[countDown]

            # Increment countups
            if action.qualityIncreaseMultiplier > 0 and innerQuiet.name in effects.countUps:
                effects.countUps[innerQuiet.name] += 1 * successProbability

            # Initialize new effects after countdowns are managed to reset them properly
            if action.type == "countup":
                effects.countUps[action.name] = 0

            if action.type == "countdown":
                effects.countDowns[action.name] = action.activeTurns

            # Sanity checks for state variables
            durabilityState = min(durabilityState, synth.recipe.durability)
            cpState = min(cpState, synth.crafter.craftPoints)

        if verbose:
            logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions))

        if debug:
            iqCnt = 0
            if innerQuiet.name in effects.countUps:
                iqCnt = effects.countUps[innerQuiet.name]
            logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i %5i %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions, iqCnt, control, qualityGain, bProgressGain, bQualityGain))

    # Penalise failure outcomes
    if progressState >= synth.recipe.difficulty:
        progressOk = True

    if cpState >= 0:
        cpOk = True

    if durabilityState >= 0 and progressState >= synth.recipe.difficulty:
        durabilityOk = True

    if trickUses <= synth.maxTrickUses:
        trickOk = True

    finalState = State(stepCount, individual[-1].name, durabilityState, cpState, qualityState, progressState,
                       wastedActions, progressOk, cpOk, durabilityOk, trickOk)

    if verbose:
        logger.log("Progress Check: %s, Durability Check: %s, CP Check: %s, Tricks Check: %s" % (progressOk, durabilityOk, cpOk, trickOk))

    if debug:
        logger.log("Progress Check: %s, Durability Check: %s, CP Check: %s, Tricks Check: %s" % (progressOk, durabilityOk, cpOk, trickOk))

    return finalState

# MoneCarlo Simulation Function
def MonteCarloSynth(individual, synth, verbose=True, debug=False, logOutput=None):
    logger = Logger(logOutput)

    # State tracking
    durabilityState = synth.recipe.durability
    cpState = synth.crafter.craftPoints
    progressState = 0
    qualityState = synth.recipe.startQuality
    stepCount = 0
    wastedActions = 0
    effects = EffectTracker()
    maxTricksUses = synth.maxTrickUses
    trickUses = 0
    condition = "Normal"

    # Strip Tricks of the Trade
    individual = [x for x in individual if x != tricksOfTheTrade]

    # Conditions
    pGood = 0.23
    pExcellent = 0.01

    # End state checks
    progressOk = False
    cpOk = False
    durabilityOk = False
    trickOk = False

    if verbose:
        logger.log("%2s %-20s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC"))
        logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions))

    if debug:
        logger.log("%2s %-20s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC", "IQ", "CTL", "QINC", "BPRG", "BQUA"))
        logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions, 0, synth.crafter.control, 0))

    for action in individual:
        # Occur regardless of dummy actions
        #==================================
        stepCount += 1

        # Add effect modifiers
        craftsmanship = synth.crafter.craftsmanship
        control = synth.crafter.control
        if innerQuiet.name in effects.countUps:
            control *= (1 + 0.2 * effects.countUps[innerQuiet.name])

        if innovation.name in effects.countDowns:
            control *= 1.5

        levelDifference = synth.crafter.level - synth.recipe.level
        if ingenuity2.name in effects.countDowns:
            levelDifference = 3
        elif ingenuity.name in effects.countDowns:
            levelDifference = 0

        if steadyHand2.name in effects.countDowns:
            successProbability = action.successProbability + 0.3        # What is effect of having both active? Assume 2 always overrides 1 but does not overwrite
        elif steadyHand.name in effects.countDowns:
            successProbability = action.successProbability + 0.2
        else:
            successProbability = action.successProbability
        successProbability = min(successProbability, 1)

        qualityIncreaseMultiplier = action.qualityIncreaseMultiplier
        if greatStrides.name in effects.countDowns:
            qualityIncreaseMultiplier *= 2

        # Condition Calculation
        if condition == "Excellent":
            condition = "Poor"
            qualityIncreaseMultiplier *= 0.5
        elif condition == "Good" or condition == "Poor":
            condition = "Normal"
        else:
            condRand = random.uniform(0,1)
            if 0 <= condRand < pExcellent:
                condition = "Excellent"
                qualityIncreaseMultiplier *= 4
            elif pExcellent <= condRand < (pExcellent + pGood):
                condition = "Good"

                if trickUses < maxTricksUses:
                    # Assumes first N good actions will always be used for ToT
                    trickUses += 1
                    cpState += 20
                else:
                    qualityIncreaseMultiplier *= 1.5

            else:
                condition = "Normal"
                qualityIncreaseMultiplier *= 1

        # Calculate final gains / losses
        success = 0
        successRand = random.uniform(0,1)
        if 0 <= successRand <= successProbability:
            success = 1

        bProgressGain = action.progressIncreaseMultiplier * synth.CalculateBaseProgressIncrease(levelDifference, craftsmanship)
        if action == flawlessSynthesis:
            bProgressGain = 40
        elif action == pieceByPiece:
            bProgressGain = (synth.recipe.difficulty - progressState)/3
        progressGain = success * bProgressGain

        bQualityGain = qualityIncreaseMultiplier * synth.CalculateBaseQualityIncrease(levelDifference, control)
        qualityGain = success * bQualityGain
        if action == byregotsBlessing:
            qualityGain *= (1 + 0.2 * effects.countUps[innerQuiet.name])

        durabilityCost = action.durabilityCost
        if wasteNot.name in effects.countDowns or wasteNot2.name in effects.countDowns:
            durabilityCost = 0.5 * action.durabilityCost

        # Occur if a dummy action
        #==================================
        if (progressState >= synth.recipe.difficulty or durabilityState <= 0) and action != dummyAction:
            wastedActions += 1

        # Occur if not a dummy action
        #==================================
        else:
            # State tracking
            progressState += progressGain
            qualityState += qualityGain
            durabilityState -= durabilityCost
            cpState -= action.cpCost

            # Effect management
            #==================================
            # Special Effect Actions
            if action == mastersMend:
                durabilityState += 30

            if action == mastersMend2:
                durabilityState += 60

            if manipulation.name in effects.countDowns and durabilityState > 0:
                durabilityState += 10

            if comfortZone.name in effects.countDowns and cpState > 0:
                cpState += 8

            if action == rumination and cpState > 0:
                if innerQuiet.name in effects.countUps and effects.countUps[innerQuiet.name] > 0:
                    cpState += (21 * effects.countUps[innerQuiet.name] - effects.countUps[innerQuiet.name]**2 + 10)/2
                    del effects.countUps[innerQuiet.name]
                else:
                    wastedActions += 1

            if action == byregotsBlessing:
                if innerQuiet.name in effects.countUps:
                    del effects.countUps[innerQuiet.name]
                else:
                    wastedActions += 1

            if action.qualityIncreaseMultiplier > 0 and greatStrides.name in effects.countDowns:
                del effects.countDowns[greatStrides.name]

            if action == tricksOfTheTrade and cpState > 0:
                trickUses += 1
                cpState += 20

            # Decrement countdowns
            for countDown in list(effects.countDowns.keys()):
                effects.countDowns[countDown] -= 1
                if effects.countDowns[countDown] == 0:
                    del effects.countDowns[countDown]

            # Increment countups
            if action.qualityIncreaseMultiplier > 0 and innerQuiet.name in effects.countUps:
                effects.countUps[innerQuiet.name] += 1 * successProbability

            # Initialize new effects after countdowns are managed to reset them properly
            if action.type == "countup":
                effects.countUps[action.name] = 0

            if action.type == "countdown":
                effects.countDowns[action.name] = action.activeTurns

            # Sanity checks for state variables
            durabilityState = min(durabilityState, synth.recipe.durability)
            cpState = min(cpState, synth.crafter.craftPoints)

        if verbose:
            logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions))

        if debug:
            iqCnt = 0
            if innerQuiet.name in effects.countUps:
                iqCnt = effects.countUps[innerQuiet.name]
            logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i %5i %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions, iqCnt, control, qualityGain, bProgressGain, bQualityGain))

    # Penalise failure outcomes
    if progressState >= synth.recipe.difficulty:
        progressOk = True

    if cpState >= 0:
        cpOk = True

    if durabilityState >= 0 and progressState >= synth.recipe.difficulty:
        durabilityOk = True

    if trickUses <= synth.maxTrickUses:
        trickOk = True

    finalState = State(stepCount, individual[-1].name, durabilityState, cpState, qualityState, progressState,
                       wastedActions, progressOk, cpOk, durabilityOk, trickOk)

    if verbose:
        logger.log("Progress Check: %s, Durability Check: %s, CP Check: %s, Tricks Check: %s" % (progressOk, durabilityOk, cpOk, trickOk))

    if debug:
        logger.log("Progress Check: %s, Durability Check: %s, CP Check: %s" % (progressOk, durabilityOk, cpOk))

    return finalState

def MonteCarloSim(individual, synth, nRuns=100, seed=None, verbose=False, debug=False, logOutput=None):
    if seed is None:
        seed = random.randint(0, 19770216)
    random.seed(seed)

    logger = Logger(logOutput)

    finalStateTracker = []
    for i in range(nRuns):
        runSynth = MonteCarloSynth(individual, synth, False, debug, logOutput)
        finalStateTracker.append(runSynth)

        if verbose:
            logger.log("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (i, "MonteCarlo", runSynth.durabilityState, runSynth.cpState, runSynth.qualityState, runSynth.progressState, runSynth.wastedActions))

    avgDurability = sum([x.durabilityState for x in finalStateTracker])/nRuns
    avgCp = sum([x.cpState for x in finalStateTracker])/nRuns
    avgQuality = sum([x.qualityState for x in finalStateTracker])/nRuns
    avgProgress = sum([x.progressState for x in finalStateTracker])/nRuns
    avgQualityPercent = avgQuality/synth.recipe.maxQuality * 100
    avgHqPercent = hqPercentFromQuality(avgQualityPercent)

    logger.log("%2s %-20s %5s %5s %5s %5s %5s" % ("", "", "DUR", "CP", "QUA", "PRG", "HQ%"))
    logger.log("%2s %-20s %5i %5i %5.1f %5.1f %5i" % ("##", "Expected Value: ", avgDurability, avgCp, avgQuality, avgProgress, avgHqPercent))

    minDurability = min([x.durabilityState for x in finalStateTracker])
    minCp = min([x.cpState for x in finalStateTracker])
    minQuality = min([x.qualityState for x in finalStateTracker])
    minProgress = min([x.progressState for x in finalStateTracker])
    minQualityPercent = minQuality/synth.recipe.maxQuality * 100
    minHqPercent = hqPercentFromQuality(minQualityPercent)

    logger.log("%2s %-20s %5i %5i %5.1f %5.1f %5i" % ("##", "Min Value: ", minDurability, minCp, minQuality, minProgress, minHqPercent))

def generateInitialGuess(synth, seqLength):
    nSynths = math.ceil(synth.recipe.difficulty / (0.9*synth.CalculateBaseProgressIncrease((synth.crafter.level-synth.recipe.level), synth.crafter.craftsmanship)) )

    myGuess = seqLength * [dummyAction]
    for i in range(nSynths):
        myGuess.pop()

    for i in range(nSynths):
        myGuess.append(basicSynth)

    myGuess[0] = innerQuiet
    myGuess[2] = hastyTouch
    myGuess[3] = hastyTouch
    myGuess[4] = hastyTouch

    return myGuess

# Define Actions
#======================================
dummyAction = Action("dummyAction", "______________")
observe = Action("observe", "Observe", cpCost=14)

basicSynth = Action("basicSynth", "Basic Synthesis", durabilityCost=10, successProbability=0.9, progressIncreaseMultiplier=1)
standardSynthesis = Action("standardSynthesis", "Standard Synthesis", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=1.5)
carefulSynthesis = Action("carefulSynthesis", "Careful Synthesis", durabilityCost=10, successProbability=1, progressIncreaseMultiplier=0.9)
carefulSynthesis2 = Action("carefulSynthesis2", "Careful Synthesis II", durabilityCost=10, successProbability=1, progressIncreaseMultiplier=1.2)
brandSynthesis = Action("brandSynthesis", "Brand Synthesis", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=2)
rapidSynthesis = Action("rapidSynthesis", "Rapid Synthesis", durabilityCost=10, cpCost=0, successProbability=0.5, progressIncreaseMultiplier=2.5)
flawlessSynthesis = Action("flawlessSynthesis", "Flawless Synthesis", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=1)
pieceByPiece = Action("pieceByPiece", "Piece By Piece", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=1)

basicTouch = Action("basicTouch", "Basic Touch", durabilityCost=10, cpCost=18, successProbability=0.7, qualityIncreaseMultiplier=1)
standardTouch = Action("standardTouch", "Standard Touch", durabilityCost=10, cpCost=32, successProbability=0.8, qualityIncreaseMultiplier=1.25)
advancedTouch = Action("advancedTouch", "Advanced Touch", durabilityCost=10, cpCost=48, successProbability=0.9, qualityIncreaseMultiplier=1.5)
hastyTouch = Action("hastyTouch", "Hasty Touch", durabilityCost=10, cpCost=0, successProbability=0.5, qualityIncreaseMultiplier=1)
byregotsBlessing = Action("byregotsBlessing", "Byregot's Blessing", durabilityCost=10, cpCost=24, successProbability=0.9, qualityIncreaseMultiplier=1)

mastersMend = Action("mastersMend", "Master's Mend", cpCost=92)
mastersMend2 = Action("mastersMend2", "Master's Mend II", cpCost=160)
rumination = Action("rumination", "Rumination")
tricksOfTheTrade = Action("tricksOfTheTrade", "Tricks Of The Trade")

innerQuiet = Action("innerQuiet", "Inner Quiet", cpCost=18, aType="countup")
manipulation = Action("manipulation", "Manipulation", cpCost=88, aType='countdown', activeTurns=3)
comfortZone = Action("comfortZone", "Comfort Zone", cpCost=66, aType='countdown', activeTurns=10)
steadyHand = Action("steadyHand", "Steady Hand", cpCost=22, aType='countdown', activeTurns=5)
steadyHand2 = Action("steadyHand2", "Steady Hand II", cpCost=25, aType='countdown', activeTurns=5)
wasteNot = Action("wasteNot", "Waste Not", cpCost=56, aType='countdown', activeTurns=4)
wasteNot2 = Action("wasteNot2", "Waste Not II", cpCost=98, aType='countdown', activeTurns=8)
innovation = Action("innovation", "Innovation", cpCost=18, aType='countdown', activeTurns=3)
greatStrides = Action("greatStrides", "Great Strides", cpCost=32, aType='countdown', activeTurns=3)
ingenuity = Action("ingenuity", "Ingenuity", cpCost=24, aType="countdown", activeTurns=5)
ingenuity2 = Action("ingenuity2", "Ingenuity II", cpCost=32, aType="countdown", activeTurns=5)

allActions = {}
for k, v in globals().items():
    if isinstance(v, Action):
        allActions[v.shortName] = v

# Call to GA
def mainGA(mySynth, penaltyWeight, seqLength, seed=None):
    if seed is None:
        seed = random.randint(0, 19770216)
    random.seed(seed)

    # Insert dummy action as padding
    myActions = list(mySynth.crafter.actions)
    myActions.insert(0, dummyAction)

    myInitialGuess = generateInitialGuess(mySynth, seqLength)

    # Evaluation function for GA using globals
    def evalSeq(individual):
        result = simSynth(individual, mySynth, verbose=False)
        penalties = 0
        fitness = 0

        # Sum the constraint violations
        penalties += result.wastedActions

        if not result.durabilityOk:
           penalties += 1

        if not result.progressOk:
            penalties += 1

        if not result.cpOk:
            penalties += 1

        if not result.trickOk:
            penalties += 1

        fitness += result.qualityState
        fitness -= penaltyWeight * penalties

        return fitness,

    # GA Stuff
    #==============================
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    creator.create("Individual", list, fitness=creator.FitnessMax)

    toolbox = base.Toolbox()

    # Attribute generator
    toolbox.register("attr_action", random.choice, myActions)

    # Structure initializers
    toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_action, seqLength)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    toolbox.register("evaluate", evalSeq)
    toolbox.register("mate", tools.cxOnePoint)
    toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05)
    toolbox.register("select", tools.selTournament, tournsize=3)

    # Set initial guess
    iniGuess = creator.Individual(myInitialGuess)
    pop = toolbox.population(n=300)
    pop.pop()
    pop.insert(0, iniGuess)

    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", tools.mean)
    stats.register("std", tools.std)
    stats.register("min", min)
    stats.register("max", max)

    # Run GA
    #==============================
    algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.2, ngen=50, stats=stats, halloffame=hof, verbose=True)

    # Print Best Individual
    #==============================
    best_ind = tools.selBest(pop, 1)[0]
    simSynth(best_ind, mySynth)

    return best_ind, pop, stats, hof

def qualityFromHqPercent(hqPercent):
    x = hqPercent
    qualityPercent = -5.6604E-6 * x**4 + 0.0015369705 * x**3 - 0.1426469573 * x**2 + 5.6122722959 * x - 5.5950384565

    return qualityPercent

def hqPercentFromQuality(qualityPercent):

    hqPercent = 1
    if qualityPercent == 0:
        hqPercent = 1
    elif qualityPercent >= 100:
        hqPercent = 100
    else:
        while qualityFromHqPercent(hqPercent) < qualityPercent and hqPercent < 100:
            hqPercent += 1

    return hqPercent

def gpEvolution(population, toolbox, cxpb, mutpb, ngen, stats=None,
             halloffame=None, verbose=False, logOutput=sys.stdout):
    """This algorithm reproduce the simplest evolutionary algorithm as
    presented in chapter 7 of [Back2000]_.

    :param population: A list of individuals.
    :param toolbox: A :class:`~deap.base.Toolbox` that contains the evolution
                    operators.
    :param cxpb: The probability of mating two individuals.
    :param mutpb: The probability of mutating an individual.
    :param ngen: The number of generation.
    :param stats: A :class:`~deap.tools.Statistics` object that is updated
                  inplace, optional.
    :param halloffame: A :class:`~deap.tools.HallOfFame` object that will
                       contain the best individuals, optional.
    :param logOutput: File-like object to which log output should be written
                      or None for no log output.
    :returns: The final population.

    It uses :math:`\lambda = \kappa = \mu` and goes as follow.
    It first initializes the population (:math:`P(0)`) by evaluating
    every individual presenting an invalid fitness. Then, it enters the
    evolution loop that begins by the selection of the :math:`P(g+1)`
    population. Then the crossover operator is applied on a proportion of
    :math:`P(g+1)` according to the *cxpb* probability, the resulting and the
    untouched individuals are placed in :math:`P'(g+1)`. Thereafter, a
    proportion of :math:`P'(g+1)`, determined by *mutpb*, is
    mutated and placed in :math:`P''(g+1)`, the untouched individuals are
    transferred :math:`P''(g+1)`. Finally, those new individuals are evaluated
    and the evolution loop continues until *ngen* generations are completed.
    Briefly, the operators are applied in the following order ::

        evaluate(population)
        for i in range(ngen):
            offspring = select(population)
            offspring = mate(offspring)
            offspring = mutate(offspring)
            evaluate(offspring)
            population = offspring

    This function expects :meth:`toolbox.mate`, :meth:`toolbox.mutate`,
    :meth:`toolbox.select` and :meth:`toolbox.evaluate` aliases to be
    registered in the toolbox.

    .. [Back2000] Back, Fogel and Michalewicz, "Evolutionary Computation 1 :
       Basic Algorithms and Operators", 2000.
    """
    # Evaluate the individuals with an invalid fitness
    invalid_ind = [ind for ind in population if not ind.fitness.valid]
    fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
    for ind, fit in zip(invalid_ind, fitnesses):
        ind.fitness.values = fit

    if halloffame is not None:
        halloffame.update(population)
    if stats is not None:
        stats.update(population)
    if verbose:
        column_names = ["gen", "evals"]
        if stats is not None:
            column_names += stats.functions.keys()
        logger = tools.EvolutionLogger(column_names)
        logger.output = logOutput
        logger.logHeader()
        logger.logGeneration(evals=len(population), gen=0, stats=stats)

    # Begin the generational process
    for gen in range(1, ngen+1):
        # Select the next generation individuals
        offspring = toolbox.select(population, len(population))

        # Variate the pool of individuals
        offspring = algorithms.varAnd(offspring, toolbox, cxpb, mutpb)

        # Evaluate the individuals with an invalid fitness
        invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
        fitnesses = toolbox.map(toolbox.evaluate, invalid_ind)
        for ind, fit in zip(invalid_ind, fitnesses):
            ind.fitness.values = fit

        # Update the hall of fame with the generated individuals
        if halloffame is not None:
            halloffame.update(offspring)

        # Replace the current population by the offspring
        population[:] = offspring

        # Update the statistics with the new population
        if stats is not None:
            stats.update(population)

        if verbose:
            logger.logGeneration(evals=len(invalid_ind), gen=gen, stats=stats)

    return population


def mainGP(mySynth, penaltyWeight, population=300, generations=100, seed=None, initialGuess = None, verbose=False, logOutput=None):
    logger = Logger(logOutput)

    # Do this be able to print the seed used
    if seed is None:
        seed = random.randint(0, 19770216)
    random.seed(seed)

    myActions = mySynth.crafter.actions

    # Create the set of primitives and terminals to set up the AST
    pset = gp.PrimitiveSet("MAIN", 0)
    pset.addPrimitive(prog2, 2)
    for action in myActions:
        pset.addTerminal(action)

    # Set up a maximization problem
    creator.create("FitnessMax", base.Fitness, weights=(1.0,))
    creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMax, pset=pset)

    toolbox = base.Toolbox()

    # Tell the GP to pull from the set of primitives when selecting genes
    toolbox.register("expr_init", gp.genFull, pset=pset, min_=1, max_=2)

    # Structure initializers
    toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.expr_init)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)

    # Create the evaluation function
    def evalSim(individual):
        # Transform the AST into a sequence of Actions
        individual = flatten_prog(individual)

        # Simulate synth
        result = simSynth(individual, mySynth, verbose=False, logOutput=logOutput)

        # Initialize tracking variables
        penalties = 0
        fitness = 0

        # Sum the constraint violations
        penalties += result.wastedActions

        if not result.durabilityOk:
           penalties += 1

        if not result.progressOk:
            penalties += 1

        if not result.cpOk:
            penalties += 1

        if not result.trickOk:
            penalties += 1

        fitness += result.qualityState
        fitness -= penaltyWeight * penalties

        return fitness,

    # more GP setup
    toolbox.register("evaluate", evalSim)
    toolbox.register("select", tools.selTournament, tournsize=7)
    toolbox.register("mate", gp.cxOnePoint)
    toolbox.register("expr_mut", gp.genRamped, min_=0, max_=2)
    toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr_mut)

    # Set up initial guess in primitive form
    pop = toolbox.population(n=population)
    if not initialGuess is None:
        tempList = []

        for item in initialGuess:
            if hasattr(item, "name"):
                for terminal in pset.terminals[None]:
                    if item == terminal.value:
                        tempList.append(terminal)
                        break

        myPrimitive = pset.primitives[None][0]
        tempList = (len(tempList)-1) * [myPrimitive] + tempList

        pop.pop(0)
        iniGuess = creator.Individual(tempList)
        pop.insert(0, iniGuess)

    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", tools.mean)
    stats.register("std", tools.std)
    stats.register("min", min)
    stats.register("max", max)

    gpEvolution(pop, toolbox, 0.5, 0.2, generations, stats, halloffame=hof, verbose=verbose, logOutput=logOutput)

    # Print Best Individual
    #==============================
    best_ind = flatten_prog(tools.selBest(pop, 1)[0])
    simSynth(best_ind, mySynth, logOutput=logOutput)

    return best_ind, pop, hof, stats


def mainRecipeWrapper():
    # Recipe Stuff
    #==============================
    # Synth details
    penaltyWeight = 10000
    population = 300
    generations = 200
    seqLength = 20
    seed = None
    monteCarloIterations = 500
    myLeatherWorkerActions = [basicSynth, basicTouch, mastersMend, innerQuiet, steadyHand, hastyTouch, tricksOfTheTrade,
                 rumination, wasteNot, manipulation, standardTouch, carefulSynthesis, mastersMend2, greatStrides, observe]
    myLeatherWorker = Crafter(25, 136, 137, 252, myLeatherWorkerActions) # Leatherworker

    myWeaverActions = [basicSynth, basicTouch, mastersMend, steadyHand, innerQuiet, hastyTouch, tricksOfTheTrade,
                 rumination, wasteNot, manipulation, carefulSynthesis, observe, standardTouch]
    myWeaver = Crafter(20, 119, 117, 243, myWeaverActions) # Weaver

    cottonYarn = Recipe(12,26,40,0,702)
    cottonCloth = Recipe(13,27,40,0,726)
    #iniGuess = [innerQuiet, steadyHand, wasteNot, hastyTouch, hastyTouch, standardTouch, basicTouch, tricksOfTheTrade, steadyHand, tricksOfTheTrade, wasteNot, hastyTouch, basicTouch, standardTouch, basicSynth]
    #iniGuess = [steadyHand, wasteNot, standardTouch, standardTouch, standardTouch, standardTouch, standardTouch, basicSynth]
    goatskinRing = Recipe(20,74,70,0,1053)   # Goatskin Ring
    cottonScarf = Recipe(15,55,70,0,807)
    #iniGuess = [innerQuiet, tricksOfTheTrade, steadyHand, carefulSynthesis, hastyTouch, standardTouch, hastyTouch, steadyHand, standardTouch, tricksOfTheTrade, wasteNot, standardTouch, standardTouch, standardTouch, basicSynth]
    cottonChausses = Recipe(14,54,60,0,751)
    #iniGuess = [innerQuiet, steadyHand, hastyTouch, tricksOfTheTrade, hastyTouch, basicTouch, carefulSynthesis, manipulation, steadyHand, standardTouch, standardTouch, tricksOfTheTrade, basicTouch, standardTouch, carefulSynthesis]
    cottonHalfGloves = Recipe(15,55,70,0,807)
    #iniGuess = [innerQuiet, tricksOfTheTrade, steadyHand, carefulSynthesis, hastyTouch, hastyTouch, standardTouch, standardTouch, steadyHand, tricksOfTheTrade, wasteNot, standardTouch, standardTouch, standardTouch, carefulSynthesis]
    cottonTurban = Recipe(13,54,60,0,726)
    #iniGuess = [innerQuiet, steadyHand, hastyTouch, tricksOfTheTrade, hastyTouch, standardTouch, standardTouch, manipulation, steadyHand, standardTouch, basicSynth, tricksOfTheTrade, hastyTouch, standardTouch, carefulSynthesis]
    cottonShepherdsTunic = Recipe(16,63,70,0,866)
    iniGuess = [innerQuiet, steadyHand, wasteNot, basicTouch, basicTouch, basicTouch, hastyTouch, tricksOfTheTrade, steadyHand, hastyTouch, basicTouch, tricksOfTheTrade, wasteNot, basicTouch, carefulSynthesis, basicTouch, basicSynth, carefulSynthesis]
    cottonKurta = Recipe(18,67,70,0,939)
    #iniGuess = [innerQuiet, steadyHand, wasteNot, basicTouch, hastyTouch, hastyTouch, hastyTouch, steadyHand, hastyTouch, tricksOfTheTrade, standardTouch, standardTouch, standardTouch, tricksOfTheTrade, rumination, mastersMend, hastyTouch, basicSynth, basicSynth, basicSynth]
    initiatesSlops = Recipe(20,74,70,0,1053)
    iniGuess = [innerQuiet, steadyHand, wasteNot, basicSynth, hastyTouch, hastyTouch, hastyTouch, steadyHand, hastyTouch, tricksOfTheTrade, standardTouch, standardTouch, standardTouch, tricksOfTheTrade, rumination, mastersMend, hastyTouch, basicSynth, basicTouch, basicSynth]


    mySynth = Synth(myWeaver, initiatesSlops, maxTrickUses=2, useConditions=True)

    # Call to GP
    best = mainGP(mySynth, penaltyWeight, population, generations, seed, iniGuess)[0]
    print("\nBest:")
    print(best)

    #print("\nProbablistic")
    #simSynth(best, mySynth, False, True)

    print("\nMonteCarlo")
    MonteCarloSim(best, mySynth, monteCarloIterations)

    #print("\nMacro")
    #print(CreateMacro(best, waitTime=3, insertTricks=False))

if __name__ == "__main__":
    mainRecipeWrapper()