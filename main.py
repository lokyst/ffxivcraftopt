# This file is part of the FFXIV CraftOptimizer
# by Rhoda Baker (rhoda.baker@gmail.com)
#
# TODO
# Initial guess for GP method
# HQ function
# UI

import random, math
from functools import partial

from deap import algorithms
from deap import base
from deap import creator
from deap import tools
from deap import gp

# ==== GP AST functions
def progn(*args):
    for arg in args:
        arg()

def prog2(out1, out2):
    return partial(progn,out1,out2)

def flatten_prog(prog):
    return [x.value for x in prog if isinstance(x, gp.Terminal)]

# ==== Macro Stuff
def CreateMacro(actionList, waitTime=3):
    macroList = [x.name for x in actionList if x != dummyAction]        # Strip dummy actions

    waitString = "/wait %i\n" % (waitTime,)
    count = 0
    macroString = ""
    for action in macroList:
        count += 1
        if count % 8 == 0:
            macroString += "\n=====================================\n\n"
        macroString += "/ac \"" + action + "\" <me>\n"
        macroString += waitString

    return macroString

# ==== Model Stuff
class Crafter:
    def __init__(self, craftsmanship=0, control=0, craftPoints=0, level=0):
        self.craftsmanship = craftsmanship
        self.control = control
        self.craftPoints = craftPoints
        self.level = level

class Recipe:
    def __init__(self, level=0, difficulty=0, durability=0, startQuality= 0, maxQuality=0):
        self.level = level
        self.difficulty = difficulty
        self.durability = durability
        self.startQuality = startQuality
        self.maxQuality = maxQuality

#noinspection PyMethodMayBeStatic
class Synth:
    def __init__(self, crafter=Crafter(), recipe=Recipe(), maxTrickUses=0, useConditions=False):
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
def simSynth(individual, synth, verbose=True, debug=False):
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
        print("%2s %-20s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC"))
        print("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions))

    if debug:
        print("%2s %-20s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC", "IQ", "CTL", "QINC", "BPRG", "BQUA"))
        print("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions, 0, synth.crafter.control, 0))

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
            print("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions))

        if debug:
            iqCnt = 0
            if innerQuiet.name in effects.countUps:
                iqCnt = effects.countUps[innerQuiet.name]
            print("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i %5i %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions, iqCnt, control, qualityGain, bProgressGain, bQualityGain))

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
        print("Progress Check: %s, Durability Check: %s, CP Check: %s, Tricks Check: %s" % (progressOk, durabilityOk, cpOk, trickOk))

    if debug:
        print("Progress Check: %s, Durability Check: %s, CP Check: %s, Tricks Check: %s" % (progressOk, durabilityOk, cpOk, trickOk))

    return finalState

# MoneCarlo Simulation Function
def MonteCarloSynth(individual, synth, verbose=True, debug=False):
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
        print("%2s %-20s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC"))
        print("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions))

    if debug:
        print("%2s %-20s %5s %5s %5s %5s %5s %5s %5s %5s %5s %5s" % ("#", "Action", "DUR", "CP", "EQUA", "EPRG", "WAC", "IQ", "CTL", "QINC", "BPRG", "BQUA"))
        print("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i" % (stepCount, "", durabilityState, cpState, qualityState, progressState, wastedActions, 0, synth.crafter.control, 0))

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
            print("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions))

        if debug:
            iqCnt = 0
            if innerQuiet.name in effects.countUps:
                iqCnt = effects.countUps[innerQuiet.name]
            print("%2i %-20s %5i %5i %5.1f %5.1f %5i %5.1f %5i %5i %5i %5i" % (stepCount, action.name, durabilityState, cpState, qualityState, progressState, wastedActions, iqCnt, control, qualityGain, bProgressGain, bQualityGain))

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
        print("Progress Check: %s, Durability Check: %s, CP Check: %s, Tricks Check: %s" % (progressOk, durabilityOk, cpOk, trickOk))

    if debug:
        print("Progress Check: %s, Durability Check: %s, CP Check: %s" % (progressOk, durabilityOk, cpOk))

    return finalState

def MonteCarloSim(individual, synth, nRuns=100, verbose=False, debug=False):
    finalStateTracker = []
    for i in range(nRuns):
        runSynth = MonteCarloSynth(individual, synth, False, debug)
        finalStateTracker.append(runSynth)

        if verbose:
            print("%2i %-20s %5i %5i %5.1f %5.1f %5i" % (i, "MonteCarlo", runSynth.durabilityState, runSynth.cpState, runSynth.qualityState, runSynth.progressState, runSynth.wastedActions))

    avgDurability = sum([x.durabilityState for x in finalStateTracker])/nRuns
    avgCp = sum([x.cpState for x in finalStateTracker])/nRuns
    avgQuality = sum([x.qualityState for x in finalStateTracker])/nRuns
    avgProgress = sum([x.progressState for x in finalStateTracker])/nRuns

    print("%2s %-20s %5i %5i %5.1f %5.1f" % ("##", "Expected Value: ", avgDurability, avgCp, avgQuality, avgProgress))

    minDurability = min([x.durabilityState for x in finalStateTracker])
    minCp = min([x.cpState for x in finalStateTracker])
    minQuality = min([x.qualityState for x in finalStateTracker])
    minProgress = min([x.progressState for x in finalStateTracker])

    print("%2s %-20s %5i %5i %5.1f %5.1f" % ("##", "Min Value: ", minDurability, minCp, minQuality, minProgress))


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

# Call to GA
def mainGA(mySynth, myActions, penaltyWeight, seqLength, seed=None):
    if seed is None:
        seed = random.randint(0, 19770216)
    random.seed(seed)

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
    print("\nRandom Seed: %i, Use Conditions: %s" % (seed, mySynth.useConditions))
    simSynth(best_ind, mySynth)

    return best_ind, pop, stats, hof

def mainGP(mySynth, myActions, penaltyWeight, seed=None):
    # Do this be able to print the seed used
    if seed is None:
        seed = random.randint(0, 19770216)
    random.seed(seed)

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
        result = simSynth(individual, mySynth, False)

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

    pop = toolbox.population(n=300)
    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", tools.mean)
    stats.register("std", tools.std)
    stats.register("min", min)
    stats.register("max", max)

    algorithms.eaSimple(pop, toolbox, 0.5, 0.2, 200, stats, halloffame=hof)

    # Print Best Individual
    #==============================
    best_ind = flatten_prog(tools.selBest(pop, 1)[0])
    print("\nRandom Seed: %i, Use Conditions: %s" % (seed, mySynth.useConditions))
    simSynth(best_ind, mySynth)

    return best_ind, pop, hof, stats


def mainRecipeWrapper():
    # Recipe Stuff
    #==============================
    # Synth details
    penaltyWeight = 10000
    seqLength = 20
    seed = None
    myCrafter = Crafter(136,137,252,25)
    #myRecipe = Recipe(10,45,60,0,629)
    myRecipe = Recipe(26,45,40,0,1332)
    mySynth = Synth(myCrafter, myRecipe, maxTrickUses=2, useConditions=True)
    myActions = [dummyAction, basicSynth, basicTouch, mastersMend, innerQuiet, steadyHand, hastyTouch, tricksOfTheTrade,
                 rumination, wasteNot, manipulation, standardTouch, carefulSynthesis, mastersMend2, greatStrides, observe]

    # Drop the dummy action when using GP
    myActions.pop(0)

    # Call to GP
    best = mainGP(mySynth, myActions, penaltyWeight, seed)[0]
    #best = [innerQuiet, tricksOfTheTrade, steadyHand, tricksOfTheTrade, greatStrides, standardTouch, manipulation,
    #        basicSynth, steadyHand, hastyTouch, hastyTouch, hastyTouch, greatStrides, standardTouch, basicSynth]
    print("\nBest:")
    print(best)

    print("\nProbablistic")
    simSynth(best, mySynth, False, True)

    print("\nMonteCarlo")
    MonteCarloSim(best, mySynth, 500)

if __name__ == "__main__":
    mainRecipeWrapper()