"""Async module for running the solver in a GAE backend queue."""


__author__ = 'Gordon Tyler <gordon@doxxx.net>'


import logging
import random
import datetime
import main
from util import StringLogOutput

from google.appengine.ext import deferred
from google.appengine.ext import ndb


def runSolver(settings, progressFeedback=None):
    logging.debug("runSolver: settings=" + repr(settings))

    result = {}
    logOutput = StringLogOutput()

    try:
        crafterActions = [main.allActions[a] for a in settings['crafter']['actions']]
        crafter = main.Crafter(settings['recipe']['cls'], settings['crafter']['level'], settings['crafter']['craftsmanship'],
                               settings['crafter']['control'], settings['crafter']['cp'], crafterActions)
        recipe = main.Recipe(settings['recipe']['level'], settings['recipe']['difficulty'],
                             settings['recipe']['durability'], settings['recipe']['startQuality'],
                             settings['recipe']['maxQuality'])
        synth = main.Synth(crafter, recipe, settings['maxTricksUses'], True)
        sequence = [main.allActions[a] for a in settings['sequence']]
        seed = settings.get('seed', None)

        if seed is None:
            seed = random.randint(0, 19770216)

        logOutput.write("Seed: %i, Use Conditions: %s\n\n" % (seed, synth.useConditions))

        logOutput.write("Genetic Program Result\n")
        logOutput.write("======================\n")

        best, finalState, _, _, _ = main.mainGP(synth, settings['solver']['penaltyWeight'], settings['solver']['population'],
                                       settings['solver']['generations'], seed, sequence, logOutput=logOutput, progressFeedback=progressFeedback)

        logOutput.write("\nMonte Carlo Result\n")
        logOutput.write("==================\n")

        main.MonteCarloSim(best, synth, nRuns=settings['maxMontecarloRuns'], seed=seed, logOutput=logOutput)

        result["finalState"] = {
            "durability": finalState.durabilityState,
            "durabilityOk": finalState.durabilityOk,
            "cp": finalState.cpState,
            "cpOk": finalState.cpOk,
            "progress": finalState.progressState,
            "progressOk": finalState.progressOk,
            "quality": finalState.qualityState,
        }
        result["bestSequence"] = [a.shortName for a in best]
    except Exception as e:
        result["error"] = str(e)
        logging.exception(e)

    result["log"] = logOutput.logText

    logging.debug("runSolver: result=" + repr(result))

    return result


class SolverTask(ndb.Model):
    settings = ndb.JsonProperty()
    generationsCompleted = ndb.IntegerProperty(default=0)
    lastProgressUpdate = ndb.DateTimeProperty()
    done = ndb.BooleanProperty(default=False)
    result = ndb.JsonProperty(default={})


def runSolverTask(taskID):
    taskKey = ndb.Key(urlsafe=taskID)
    task = taskKey.get()

    def updateProgress(generationsCompleted):
        # update at most once a second
        now = datetime.datetime.utcnow()
        if task.lastProgressUpdate is None or (now - task.lastProgressUpdate).total_seconds() >= 0.9:
            task.generationsCompleted = generationsCompleted
            task.lastProgressUpdate = now
            task.put()


    result = runSolver(task.settings, progressFeedback=updateProgress)
    task.done = True
    task.result = result
    task.put()


def queueTask(settings):
    task = SolverTask(settings=settings)
    taskKey = task.put()
    taskID = taskKey.urlsafe()
    deferred.defer(runSolverTask, taskKey.urlsafe(), _queue="solverqueue", _target="solverbackend")
    return taskID
