"""Solver Web Service.
"""

import random


__author__ = 'Gordon Tyler <gordon@doxxx.net>'

import webapp2
import logging
import json
import main

from google.appengine.ext import deferred
from google.appengine.ext import ndb


greetings = [
    {
        "id": 0,
        "greeting": "hello",
    },
    {
        "id": 1,
        "greeting": "yo!",
    },
]


class StringLogOutput(object):
    def __init__(self):
        self.logText = ""

    def write(self, s):
        self.logText = self.logText + s


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


class BaseHandler(webapp2.RequestHandler):
    def options(self):
        self.response.headers['Access-Control-Allow-Methods'] = 'POST'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        self.response.headers['Content-Type'] = 'application/json'

    def writeHeaders(self):
        self.response.headers['Content-Type'] = 'application/json'
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Cache-Control'] = 'max-age=0, no-cache, no-store'


class SimulationHandler(BaseHandler):
    def post(self):
        settings = json.loads(self.request.body)
        logging.debug("settings=" + repr(settings))

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
            logOutput.write("Probabilistic Result\n")
            logOutput.write("====================\n")

            finalState = main.simSynth(sequence, synth, logOutput=logOutput)

            result["finalState"] = {
                "durability": finalState.durabilityState,
                "durabilityOk": finalState.durabilityOk,
                "cp": finalState.cpState,
                "cpOk": finalState.cpOk,
                "progress": finalState.progressState,
                "progressOk": finalState.progressOk,
                "quality": finalState.qualityState,
            }

            logOutput.write("\nMonte Carlo Result\n")
            logOutput.write("==================\n")

            main.MonteCarloSim(sequence, synth, nRuns=settings['maxMontecarloRuns'], seed=seed, logOutput=logOutput)
        except Exception as e:
            result["error"] = str(e)
            logging.exception(e)
            self.response.status = 500

        result["log"] = logOutput.logText

        logging.debug("result=" + repr(result))

        self.writeHeaders()
        self.response.write(json.dumps(result))


class SolverHandler(BaseHandler):
    def post(self):
        settings = json.loads(self.request.body)
        logging.debug("settings=" + repr(settings))

        result = runSolver(settings)

        if result.has_key("error"):
            self.response.status = 500

        self.writeHeaders()
        self.response.write(json.dumps(result))


class AsyncSolverTask(ndb.Model):
    settings = ndb.JsonProperty()
    generationsCompleted = ndb.IntegerProperty()
    done = ndb.BooleanProperty()
    result = ndb.JsonProperty()


def runSolverAsync(taskID):
    taskKey = ndb.Key(urlsafe=taskID)
    task = taskKey.get()

    def updateProgress(generationsCompleted):
        task.generationsCompleted = generationsCompleted
        task.put()

    result = runSolver(task.settings, progressFeedback=updateProgress)
    task.done = True
    task.result = result
    task.put()


class SolverAsyncHandler(BaseHandler):
    def get(self):
        taskID = self.request.get("taskID")
        taskKey = ndb.Key(urlsafe=taskID)

        task = taskKey.get()

        if task:
            result = {
                "generationsCompleted": task.generationsCompleted,
                "done": task.done,
                "result": task.result
            }
            if task.done:
                taskKey.delete()
        else:
            self.response.status = 500
            result = {
                "result": {
                    "error": "Unknown task: %s" % (taskID,)
                }
            }

        logging.debug("SolverAsyncHandler.get: result=" + repr(result))

        self.writeHeaders()
        self.response.write(json.dumps(result))

    def post(self):
        settings = json.loads(self.request.body)

        task = AsyncSolverTask(settings=settings)
        taskKey = task.put()
        taskID = taskKey.urlsafe()
        deferred.defer(runSolverAsync, taskKey.urlsafe(), _queue="solverqueue", _target="solverbackend")

        result = {
            "taskID": taskID
        }

        logging.debug("SolverAsyncHandler.post: result=" + repr(result))

        self.writeHeaders()
        self.response.write(json.dumps(result))


application = webapp2.WSGIApplication([
    ('/simulation', SimulationHandler),
    ('/solver', SolverHandler),
    ('/async_solver', SolverAsyncHandler),
], debug=__debug__)
