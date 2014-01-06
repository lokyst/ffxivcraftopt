# ffxivcraftopt - The FFXIV Crafting Optimizer

Given the crafter's details, a list of available actions and the details of the recipe, the FFXIV Crafting Optimizer uses a genetic algorithm to determine a sequence of actions that will maximize the expected value of the final quality of the synthesis. Because the solver is not deterministic and crafting itself has random elements, the solution provided is not guaranteed, especially if Tricks of the Trade is used. Use at your own risk!

## How to use ffxivcraftopt

After setting up Crafter, Recipe and Synthesis objects, the function mainGP can be used to run a Genetic Program to find a sequence that will maximize the final quality. See mainRecipeWrapper in main.py for an example.

It also provides a web service interface as a google app engine module in webapi.py. The web user interface project is at [ffxiv-craft-opt-web](https://github.com/doxxx/ffxiv-craft-opt-web)

## References for crafting formulae etc.

* [Final Fantasy XIV](http://na.finalfantasyxiv.com/)
* [Distributed Evolutionary Algorithms in Python](https://code.google.com/p/deap/)
* [Bluegartr - The Crafting Thread](http://www.bluegartr.com/threads/117684-The-crafting-thread.)
* [FFXIV subreddit](http://www.reddit.com/r/ffxiv/)
