import numpy as np
from initializeWorkerSequences import create_sequence
from matplotlib import pyplot as plt

"""
INSPECT DIAGNOSTICS OF HOW SEQUENCES ARE CONSTRUCTED

This code deals with plotting some diagnostics of how create_sequence preconstructs the memory game sequences, 
by simulating a large number of calls to this function. 

One thing we can infer from this is how likely it is to assign repeats to certain places in the sequence. This way, 
we can spot if zones are way too likely/unlikely to have repeats in them and adjust the create_sequence algorithm 
accordingly. 

"""

# %% Settings ---------------------------------------------------------------------------------------------------------
num_targets = 60
num_fillers = 57
num_vigs = 19
min_dist_targets = 35
max_dist_targets = 140
min_dist_vigs = 1
max_dist_vigs = 4
num_simulations = 1000

type_map = {
    "target": 1,
    "target repeat": 2,
    "filler": 3,
    "vig": 4,
    "vig repeat": 5
}

inv_type_map = {v: k for k, v in type_map.items()}

# %% Simulate stimulus set ---------------------------------------------------------------------------------------------
images_selected = {"targets": list(range(num_targets)),
                   "fillers": list(range(num_targets, num_targets + num_fillers)),
                   "vigs": list(range(num_targets + num_fillers, num_targets + num_fillers + num_vigs))}

# %% Simulate sequences ------------------------------------------------------------------------------------------------
simulations = np.zeros((num_simulations, num_targets * 2 + num_fillers + num_vigs * 2))

for i in range(num_simulations):
    _, types = create_sequence(images_selected, min_dist_targets, max_dist_targets, min_dist_vigs, max_dist_vigs)
    simulations[i, :] = [type_map[x] for x in types]

# %% Plots -------------------------------------------------------------------------------------------------------------
x = np.arange(num_targets * 2 + num_fillers + num_vigs * 2)

# region Repeat probabilities
repeat_probs = ((simulations == 1) | (simulations == 2)).sum(axis=0)/num_simulations
plt.bar(x, repeat_probs)
plt.xlabel("place in sequence")
plt.ylabel("probability of repeat")
plt.savefig("repeat_probabilities")
plt.clf()
# endregion

