"""Hello World API.
"""

__author__ = 'Gordon Tyler <gordon@doxxx.net>'


import webapp2
import logging
import json
import main


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


class Logger:
    def __init__(self):
        self.logText = ""

    def log(self, s):
        self.logText = self.logText + s + "\n"


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
        logging.info("settings=" + repr(settings))

        crafterActions = [main.allActions[a] for a in settings['crafter']['actions']]
        crafter = main.Crafter(settings['crafter']['level'], settings['crafter']['craftsmanship'], settings['crafter']['control'], settings['crafter']['cp'], crafterActions)
        recipe = main.Recipe(settings['recipe']['level'], settings['recipe']['difficulty'], settings['recipe']['durability'], settings['recipe']['startQuality'], settings['recipe']['maxQuality'])
        synth = main.Synth(crafter, recipe, settings['maxTricksUses'], True)
        sequence = [main.allActions[a] for a in settings['sequence']]

        probabilisticLog = Logger()
        main.simSynth(sequence, synth, log=probabilisticLog.log)

        monteCarloLogger = Logger()
        main.MonteCarloSim(sequence, synth, nRuns = settings['simulation']['maxMontecarloRuns'], log=monteCarloLogger.log)

        result = {
            "probabilisticLog": probabilisticLog.logText,
            "monteCarloLog": monteCarloLogger.logText,
        }

        logging.info("result=" + repr(result))

        self.writeHeaders()
        self.response.write(json.dumps(result))


class SolverHandler(BaseHandler):
    def post(self):
        settings = json.loads(self.request.body)
        logging.info("settings=" + repr(settings))

        crafterActions = [main.allActions[a] for a in settings['crafter']['actions']]
        crafter = main.Crafter(settings['crafter']['level'], settings['crafter']['craftsmanship'], settings['crafter']['control'], settings['crafter']['cp'], crafterActions)
        recipe = main.Recipe(settings['recipe']['level'], settings['recipe']['difficulty'], settings['recipe']['durability'], settings['recipe']['startQuality'], settings['recipe']['maxQuality'])
        synth = main.Synth(crafter, recipe, settings['maxTricksUses'], True)
        sequence = [main.allActions[a] for a in settings['sequence']]
        logger = Logger()

        best = main.mainGP(synth, settings['solver']['penaltyWeight'], settings['solver']['population'], settings['solver']['generations'], settings['solver']['seed'], sequence, logger.log)[0]

        result = {
            "log": logger.logText,
        }

        logging.info("result=" + repr(result))

        self.writeHeaders()
        self.response.write(json.dumps(result))


application = webapp2.WSGIApplication([
    ('/simulation', SimulationHandler),
    ('/solver', SolverHandler),
], debug=True)
