"""GAE Web Handlers for Simulation and Solver web services."""


__author__ = 'Gordon Tyler <gordon@doxxx.net>'


import logging
import webapp2
import json
import random
import main
import async
from util import StringLogOutput

from google.appengine.ext import ndb


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

        taskID = async.queueTask(settings)

        result = {
            "taskID": taskID
        }

        logging.debug("SolverAsyncHandler.post: result=" + repr(result))

        self.writeHeaders()
        self.response.write(json.dumps(result))


application = webapp2.WSGIApplication([
    ('/simulation', SimulationHandler),
    ('/solver', SolverHandler),
], debug=__debug__)
