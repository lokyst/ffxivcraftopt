#    This file is part of DEAP.
#
#    DEAP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    DEAP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with DEAP. If not, see <http://www.gnu.org/licenses/>.

import random, math

from deap import algorithms
from deap import base
from deap import creator
from deap import tools

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
    def __init__(self, name, durabilityCost=0, cpCost=0, successProbability=1.0, qualityIncreaseMultiplier=0.0, progressIncreaseMultiplier=0.0, aType='immediate', activeTurns=1):
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

# Simulation Function
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

            if action == rumination:
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

            if action == tricksOfTheTrade:
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
        print("Progress Check: %s, Durability Check: %s, CP Check: %s" % (progressOk, durabilityOk, cpOk))

    return finalState

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
dummyAction = Action("______________")
observe = Action("Observe", cpCost=14)

basicSynth = Action("Basic Synthesis", durabilityCost=10, successProbability=0.9, progressIncreaseMultiplier=1)
standardSynthesis = Action("Standard Synthesis", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=1.5)
carefulSynthesis = Action("Careful Synthesis", durabilityCost=10, successProbability=1, progressIncreaseMultiplier=0.9)
carefulSynthesis2 = Action("Careful Synthesis II", durabilityCost=10, successProbability=1, progressIncreaseMultiplier=1.2)
brandSynthesis = Action("Brand Synthesis", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=2)
rapidSynthesis = Action("Rapid Synthesis", durabilityCost=10, cpCost=0, successProbability=0.5, progressIncreaseMultiplier=2.5)
flawlessSynthesis = Action("Flawless Synthesis", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=1)
pieceByPiece = Action("Piece By Piece", durabilityCost=10, cpCost=15, successProbability=0.9, progressIncreaseMultiplier=1)

basicTouch = Action("Basic Touch", durabilityCost=10, cpCost=18, successProbability=0.7, qualityIncreaseMultiplier=1)
standardTouch = Action("Standard Touch", durabilityCost=10, cpCost=32, successProbability=0.8, qualityIncreaseMultiplier=1.25)
advancedTouch = Action("Advanced Touch", durabilityCost=10, cpCost=48, successProbability=0.9, qualityIncreaseMultiplier=1.5)
hastyTouch = Action("Hasty Touch", durabilityCost=10, cpCost=0, successProbability=0.5, qualityIncreaseMultiplier=1)
byregotsBlessing = Action("Byregot's Blessing", durabilityCost=10, cpCost=24, successProbability=0.9, qualityIncreaseMultiplier=1)

mastersMend = Action("Master's Mend", cpCost=92)
mastersMend2 = Action("Master's Mend II", cpCost=160)
rumination = Action("Rumination")
tricksOfTheTrade = Action("Tricks Of The Trade")

innerQuiet = Action("Inner Quiet", cpCost=18, aType="countup")
manipulation = Action("Manipulation", cpCost=88, aType='countdown', activeTurns=3)
comfortZone = Action("Comfort Zone", cpCost=66, aType='countdown', activeTurns=10)
steadyHand = Action("Steady Hand", cpCost=22, aType='countdown', activeTurns=5)
steadyHand2 = Action("Steady Hand II", cpCost=25, aType='countdown', activeTurns=5)
wasteNot = Action("Waste Not", cpCost=56, aType='countdown', activeTurns=4)
wasteNot2 = Action("Waste Not II", cpCost=98, aType='countdown', activeTurns=8)
innovation = Action("Innovation", cpCost=18, aType='countdown', activeTurns=3)
greatStrides = Action("Great Strides", cpCost=32, aType='countdown', activeTurns=3)
ingenuity = Action("Ingenuity", cpCost=24, aType="countdown", activeTurns=5)
ingenuity2 = Action("Ingenuity II", cpCost=32, aType="countdown", activeTurns=5)

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

    return pop, stats, hof

def mainSim(mySynth):
    # Test cases
    #test = [innerQuiet, steadyHand, wasteNot, hastyTouch, hastyTouch, hastyTouch, hastyTouch,
    #         steadyHand, wasteNot, hastyTouch, hastyTouch, basicSynth]
    #
    #test = [innerQuiet, steadyHand, wasteNot, hastyTouch, hastyTouch, hastyTouch, hastyTouch,
    #         steadyHand, wasteNot, byregotsBlessing, basicSynth]
    #
    #test = [innerQuiet, steadyHand, wasteNot, hastyTouch, hastyTouch, hastyTouch, byregotsBlessing, innerQuiet,
    #         steadyHand, wasteNot, hastyTouch, hastyTouch, basicSynth]
    #
    #test = [innerQuiet, steadyHand, wasteNot2, wasteNot, advancedTouch, advancedTouch, advancedTouch, advancedTouch,
    #        advancedTouch, advancedTouch, advancedTouch, advancedTouch, basicSynth]
    #
    #test = [innerQuiet, steadyHand2, wasteNot2, basicTouch, basicTouch, basicTouch, basicTouch, steadyHand2, greatStrides, byregotsBlessing, standardSynthesis]

    test = [innerQuiet, steadyHand2, ingenuity2, ingenuity, basicTouch, basicTouch, basicTouch, basicTouch, tricksOfTheTrade, basicSynth]

    simSynth(test, mySynth, False, True)

def mainRecipeWrapper():
    # Recipe Stuff
    #==============================
    # Synth details
    penaltyWeight = 10000
    seqLength = 20
    myCrafter = Crafter(136,137,252,25)
    #myRecipe = Recipe(10,45,60,0,629)
    myRecipe = Recipe(26,45,40,0,1332)
    mySynth = Synth(myCrafter, myRecipe, maxTrickUses=2, useConditions=True)
    myActions = [dummyAction, basicSynth, basicTouch, mastersMend, innerQuiet, steadyHand, hastyTouch, tricksOfTheTrade,
                 rumination, wasteNot, manipulation, standardTouch, carefulSynthesis, mastersMend2, greatStrides, observe]

    # Call to GA
    mainGA(mySynth, myActions, penaltyWeight, seqLength)

if __name__ == "__main__":
    mainRecipeWrapper()