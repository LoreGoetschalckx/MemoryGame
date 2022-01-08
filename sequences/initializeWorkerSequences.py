import math
import os
import random
import collections
import json
import argparse
import numpy as np
import copy

"""
PRECONSTRUCT MEMORY GAME SEQUENCES

The code deals with preconstructing sequences for the memory game. More precisely, it creates "tracks" that can be 
assigned to a player of the game. A track consists of multiple sequences (blocks) that define which image a player 
will see on which trial. Every track is saved as a json file. The number of tracks to be generated is determined by 
the num_workers argument. This should correspond roughly to how many players you want to participate in the game. Only 
roughly, cause you can construct more later if you need more. 

Each json file contains a dictionary with the following keys: - sequences: this is a list of lists. Each sublist 
represents one block/sequence. The elements in the sublists are paths to images. - types: this a list of lists. Each 
sublist represents one block/sequence. The elements in the sublists represent the trial types: target, 
target repeat, filler, vigilance, vigilance repeat.

NOTE1: this script was written to construct sequences in a scenario where the total image collection is clustered into 
smaller sets and we only want to show one image of each set per worker. It is assumed that the images of a cluster 
have their own subdirectory in os.path.join(image_root, target_dir) (analogously for fillers). If you don't have
such clustering, you can set clustering to False.


NOTE2: The code was only ever tested with the default settings. It might not yield nice sequences (e.g., in terms of 
where repeats are likely to occur) with different ones.
 """


# %% Sequence building functions --------------------------------------------------------------------------------------

# region Main sequence building function
def create_sequence(images, min_dist_targets, max_dist_targets, min_dist_vigs, max_dist_vigs):
    """
    Creates one track for the memory game.

    :param images: dict with keys: ["targets", "vigs", "fillers"] and values: lists of stimuli to be used
    :param min_dist_targets: minimum distance between target and repeat (difference in index)
    :param max_dist_targets: maximum distance between target and repeat (difference in index)
    :param min_dist_vigs: minimum distance between vig and repeat (difference in index)
    :param max_dist_vigs: max distance between vig and repeat (difference in index)
    :return: two lists. One with the actual image sequences for one track. The other describing trial types.
    """

    # Compute additional sequence parameters from images
    num_targets = len(images["targets"])
    num_fillers = len(images["fillers"])
    num_vigs = len(images["vigs"])
    num_places = num_targets * 2 + num_vigs * 2 + num_fillers  # number of places (trials) in the sequence

    # Some settings (hard-coded)
    num_first_targets = 25
    num_first_fillers = int((float(6) / 10) * num_fillers)
    max_attempts = 10

    success = False

    for i in range(max_attempts):
        try:

            sequence = [None] * num_places  # initializing sequence to be filled with images
            types = [None] * num_places  # initializing list of trial types for this sequence (e.g., "target repeat")
            places_available = list(range(num_places))  # available places

            # Distribute vigilance trials
            # Need to do these first because range of allowed distances is much smaller
            vigs_places = distribute_vigs(places_available, num_vigs, num_places, min_dist_vigs, max_dist_vigs)
            allocate_images(sequence, types, images["vigs"], vigs_places, label="vig")

            # Distribute first set of targets
            # Need to ensure enough target presentations at the start to get at least a few early repeats
            first_target_places = distribute_first_targets(places_available, num_first_targets, min_dist_targets,
                                                           max_dist_targets, start_phase_length=min_dist_targets)
            allocate_images(sequence, types, images["targets"], first_target_places, label="target")

            # Distribute first set of fillers
            # Need to place some fillers in the second half of the sequence to avoid having only repeats there
            first_filler_places = distribute_first_fillers(places_available, num_first_fillers, num_places)
            allocate_images(sequence, types, images["fillers"], first_filler_places, label="filler")

            # Distribute remaining targets
            target_places = distribute_targets(places_available, num_targets - num_first_targets, num_places,
                                               min_dist_targets, max_dist_targets, start_phase_length=min_dist_targets)
            allocate_images(sequence, types, images["targets"][num_first_targets:], target_places, label="target")

            # Distribute remaining fillers
            filler_places = distribute_fillers(places_available, num_fillers - num_first_fillers)
            allocate_images(sequence, types, images["fillers"][num_first_fillers:], filler_places, label="filler")

            # Leave attempt loop
            success = True
            break  # no need for another attempt if no error was caught

        except Exception as e:
            print(e)

    if not success:
        raise Exception("Failure! No solution found in " + str(max_attempts) + " attempts!")

    approved, text = check_sequence(sequence, images, min_dist_targets, max_dist_targets, min_dist_vigs, max_dist_vigs)
    if not approved:
        raise Exception(text)
    else:
        print("Success! Solution found after ", i + 1, " attempts.")

    return sequence, types


# endregion

# region Functions selecting places in the sequence
def distribute_vigs(places_available, num, num_places, min_dist, max_dist):
    """
    Chooses places to put vigs

    :param places_available: sorted list of places in the sequence that are still available
    :param num: number of places to choose
    :param num_places: total number of places in the sequence (including unavailable ones)
    :param min_dist: minimum distance between first occurrence and repeat (difference in index)
    :param max_dist: maximum distance between first occurrence and repeat (difference in index)
    :return: list of chosen places
    """
    # Sampling weights (higher weights for early places)
    probs = np.concatenate([np.repeat(3, int(70 /float(215) * num_places)),
                        np.repeat(1, int(110 /float(215) * num_places)),
                        np.repeat(0.3, int(35 /float(215) * num_places))])
    probs = np.float64(probs) / np.sum(probs)

    # Choose places
    chosen_places = list(np.random.choice(places_available, num, replace=False, p=probs))
    for place in chosen_places:
        places_available.remove(place)
    chosen_places = [[x] for x in chosen_places]

    # Choose places for repeats
    chosen_places = allocate_repeats(chosen_places, places_available, min_dist, max_dist)

    return chosen_places


def distribute_first_targets(places_available, num, min_dist, max_dist, start_phase_length):
    """
    Chooses places for a first batch of targets

    For a first batch of targets, places in the start phase of the sequence are chosen (i.e, region a the beginning
    of the sequence). This is done to ensure that repeats can happen relatively early in the sequence too and won't
    all be pushed toward the end of the sequence.

    :param places_available: sorted list of places in the sequence that are still available
    :param num: number of places to choose
    :param min_dist: minimum distance between first occurrence and repeat (difference in index)
    :param max_dist: maximum distance between first occurrence and repeat (difference in index)
    :param start_phase_length: defines the region that will be considered close enough to the start
    :return: list of chosen places
    """
    # Find available start phase places
    start_phase_start = 0
    start_phase_end = start_phase_length
    start_phase_places = [x for x in places_available if start_phase_start <= x <= start_phase_end]
    random.shuffle(start_phase_places)  # not strictly necessary if the images themselves are shuffled

    # Choose places
    # First take places from the start phase
    chosen_places = start_phase_places[0:min(num, len(start_phase_places))]
    for place in chosen_places:
        places_available.remove(place)
    # If they run out, pick any other available position
    for i in range(num - len(chosen_places)):
        chosen_places.append(places_available.pop(random.randrange(len(places_available))))  # pop and append
    chosen_places = [[x] for x in chosen_places]

    # Choose places for repeats
    chosen_places = allocate_repeats(chosen_places, places_available, min_dist, max_dist)

    return chosen_places


def distribute_first_fillers(places_available, num, num_places):
    """
    Chooses places for a first batch of fillers

    For a first batch of fillers, places in the second half of the sequence are chosen. This is done to limit the
    predominance of repeat trials late in the sequence.

    :param places_available: sorted list of places in the sequence that are still available
    :param num: number of places to choose
    :param num_places: total number of places in the sequence (including unavailable ones)
    :return: list of chosen places
    """
    # Find available places in second half of sequence
    second_half_places = [x for x in places_available if x >= int(num_places / 2)]

    # Choose places
    chosen_places = np.random.choice(second_half_places, num, replace=False)
    for place in chosen_places:
        places_available.remove(place)
    chosen_places = [[x] for x in chosen_places]

    return chosen_places


def distribute_targets(places_available, num, num_places, min_dist, max_dist, start_phase_length):
    """
    Chooses places for targets

    This function is used for those targets that weren't in the first batch. To avoid long trains of consecutive
    trials of the same type, they are temporarily assigned places at equal intervals. Those temporary places are
    still shifted somewhat later in the function (also to avoid creating a pattern).

    :param places_available: sorted list of places in the sequence that are still available
    :param num: number of places to choose
    :param num_places: total number of places in the sequence (including unavailable ones)
    :param min_dist: minimum distance between first occurrence and repeat (difference in index)
    :param max_dist: maximum distance between first occurrence and repeat (difference in index)
    :param start_phase_length: defines the region that will be considered close enough to the start
    :return: list of chosen places
    """
    # Define increment so we can distribute remaining targets roughly evenly
    increment = int(round(float(num_places - start_phase_length) / num))  # roughly how far apart to position *different* targets

    # Choose places
    # First, pick temporary places (might be unavailable) approximately equally far apart
    # Then, find available places roughly matching those temporary places
    chosen_places = [random.randint(start_phase_length, start_phase_length + increment)]
    for i in range(1, num):
        chosen_places.append(chosen_places[i - 1] + increment)
    chosen_places = [[find_free_place(places_available=places_available, desired_place=x)] for x in chosen_places]

    # Choose places for repeats
    chosen_places = allocate_repeats(chosen_places, places_available, min_dist, max_dist)

    return chosen_places


def distribute_fillers(places_available, num):
    """
    Chooses places for fillers

    This function is used for those fillers that weren't in the first batch.

    :param places_available: sorted list of places in the sequence that are still available
    :param num: number of places to choose
    :return: list of chosen places
    """
    chosen_places = places_available[:num]
    chosen_places = [[place] for place in chosen_places]
    return chosen_places


def allocate_repeats(first_places, places_available, min_dist, max_dist):
    """
    Chooses places to for the repeats to go with the chosen first places

    :param first_places: list of places for the first occurrences
    :param places_available: sorted list of places in the sequence that are still available
    :param min_dist: minimum distance between first occurrence and repeat (difference in index)
    :param max_dist: maximum distance between first occurrence and repeat (difference in index)
    :return: list of chosen places
    """

    for idx in range(len(first_places)):
        # Looking for places forward in the sequence
        min_place = first_places[idx][0] + min_dist
        max_place = first_places[idx][0] + max_dist
        forward_options = [i for i in places_available if min_place <= i <= max_place]

        # Looking for places backward in the sequence (reversing role of first occurrence and repeat)
        min_place = first_places[idx][0] - max_dist
        max_place = first_places[idx][0] - min_dist
        backward_options = [i for i in places_available if min_place <= i <= max_place]

        # Choose place
        chosen_place = random.choice(forward_options + backward_options)
        first_places[idx].append(chosen_place)
        first_places[idx].sort()
        places_available.remove(chosen_place)

    return first_places


# endregion

# region Helper functions
def find_free_place(places_available, desired_place):
    """
    Find place in sequence that is available and nearby.

    This function checks if desired_place is in the list of places that are still available and returns
    desired_place if so. If not, it returns the closest, higher place that is. If there are no higher ones,
    it returns the lowest place in places_available.

    :param places_available: sorted list of places in the sequence that are still available
    :param desired_place: place to check
    :return chosen place
    """
    if desired_place in places_available:
        places_available.remove(desired_place)
        return desired_place

    for k in places_available:
        if k > desired_place:  # assuming places_available is sorted
            places_available.remove(k)
            return k

    chosen_place = min(places_available)
    places_available.remove(min(places_available))
    return chosen_place


def allocate_images(sequence, types, images, places, label):
    """
    Puts images in their assigned places in the sequence and type labels in the corresponding places in the types list.

    :param sequence: list to be turned into a valid game sequence
    :param types: list to be turned into a description of the trial types
    :param images: list of stimuli to be allocated
    :param places: list of places to assign images to
    :param label: label to use for trial type in types
    """
    for i in range(len(places)):
        sequence[places[i][0]] = images[i]
        types[places[i][0]] = label
        if len(places[i]) > 1:
            sequence[places[i][1]] = images[i]
            types[places[i][1]] = label + " repeat"


# endregion

# region Validation functions
def get_distances(sequence):
    """
    Get distance between two occurrences of each unique element in sequence

    Returns 0 if it only occurs once, returns the distance between the last two occurrences if element occurs more
    than twice 0 if only occurs once

    :param sequence: list
    :return: dictionary with (element, distance) as key, value pairs
    """
    distances = dict((s, {}) for s in set(sequence))
    for i in range(len(sequence)):
        distances[sequence[i]]["distance"] = i - distances[sequence[i]].get("last index", i)
        distances[sequence[i]]["last index"] = i
    return {key: value["distance"] for (key, value) in distances.items()}  # dropping "last index" field


def get_occurrences(track):
    """
    Get indices of occurrences of each unique element in two-level nested list (track)

    Returns 0 if it only occurs once, returns the distance between the last two occurrences if element occurs more
    than twice 0 if only occurs once

    :param track: two-level nested list (assumes each first order list element is a list itself)
    :return: dict
    """
    track_flat = [item for sublist in track for item in sublist]
    occurrences = dict((s, {"sequence_index": [], "place_index": []}) for s in set(track_flat))

    for sequence_index in range(len(track)):
        for place_index in range(len(track[sequence_index])):
            occurrences[track[sequence_index][place_index]]["sequence_index"].append(sequence_index)
            occurrences[track[sequence_index][place_index]]["place_index"].append(place_index)

    return occurrences


def check_sequence(sequence, images, min_dist_targets, max_dist_targets, min_dist_vigs, max_dist_vigs):
    counts = collections.Counter(sequence)
    distances = get_distances(sequence)

    if None in sequence:
        return False, "Not all places in the sequence have been filled"
    if not all([counts[target] == 2 for target in images["targets"]]):
        return False, "Not every target appears exactly twice"
    if not all(counts[vig] == 2 for vig in images["vigs"]):
        return False, "Not every vig appears exactly twice"
    if not all(counts[filler] == 1 for filler in images["fillers"]):
        return False, "Not every filler appears exactly once"
    if not all([min_dist_targets <= distances[target] <= max_dist_targets for target in images["targets"]]):
        return False, "Not every target repeat is within the allowed distance range"
    if not all([min_dist_vigs <= distances[vig] <= max_dist_vigs for vig in images["vigs"]]):
        return False, "Not every vigilance repeat is within the allowed distance range"

    return True, "All good"


def check_track(images, track, types):
    images_flat = {k: [dictionary[k] for dictionary in images] for k in images[0]}  # list of dicts to dict of lists
    images_flat = {k: [item for sublist in images_flat[k] for item in sublist] for k in images_flat}  # flatten lists
    occurrences = get_occurrences(track)

    # Checking occurrences
    if not all([len(set(occurrences[target]["place_index"])) == 2 for target in images_flat["targets"]]):
        return False, "Failed track level check. Not every target appears exactly twice"
    if not all([len(set(occurrences[target]["sequence_index"])) == 1 for target in images_flat["targets"]]):
        return False, "Failed track level check. Not every target appears in exactly one sequence within the track"
    if not all([len(set(occurrences[filler]["place_index"])) == 1 for filler in images_flat["fillers"]]):
        return False, "Failed track level check. Not every filler appears exactly once"
    if not all([len(set(occurrences[vig]["place_index"])) == 2 for vig in images_flat["vigs"]]):
        return False, "Failed track level check. Not every vig appears exactly twice"
    if not all([len(set(occurrences[vig]["sequence_index"])) == 1 for vig in images_flat["vigs"]]):
        return False, "Failed track level check. Not every vig appears in exactly one sequence within the track"

    # Checking if every place has the right label in types
    if not all([types[occurrences[target]["sequence_index"][0]][occurrences[target]["place_index"][0]] == "target" for
                target in images_flat["targets"]]):
        return False, "Failed track level check. Not every first occurrence of a target is labeled correctly in types"
    if not all(
            [types[occurrences[target]["sequence_index"][1]][occurrences[target]["place_index"][1]] == "target repeat"
             for target in images_flat["targets"]]):
        return False, "Failed track level check. Not every repeat occurrence of a target is labeled correctly in types"
    if not all([types[occurrences[vig]["sequence_index"][0]][occurrences[vig]["place_index"][0]] == "vig" for vig in
                images_flat["vigs"]]):
        return False, "Failed track level check. Not every first occurrence of a vig is labeled correctly in types"
    if not all(
            [types[occurrences[vig]["sequence_index"][1]][occurrences[vig]["place_index"][1]] == "vig repeat" for vig
             in images_flat["vigs"]]):
        return False, "Failed track level check. Not every repeat occurrence of a vig is labeled correctly in types"
    if not all([types[occurrences[filler]["sequence_index"][0]][occurrences[filler]["place_index"][0]] == "filler" for
                filler in
                images_flat["fillers"]]):
        return False, "Failed track level check. Not every first occurrence of a filler is labeled correctly in types"

    return True, "All good"


# endregion

if __name__ == "__main__":
# %% Collect command line arguments ----------------------------------------------------------------------------------
    parser = argparse.ArgumentParser()
    parser.add_argument('--image_root', type=str, default="../stimuli/memcat", help='dir containing target images')
    parser.add_argument('--target_dir', type=str, default="targets", help='sub-dir containing target images')
    parser.add_argument('--filler_dir', type=str, default="fillers", help='sub-dir containing filler images')
    parser.add_argument('--track_dir', type=str, default="./sequenceFiles", help='dir store the worker sequences in')
    parser.add_argument('--num_targets', type=int, default=60, help='how many target images needed for one block')
    parser.add_argument('--num_fillers', type=int, default=57, help='how many filler images needed for one block')
    parser.add_argument('--num_vigs', type=int, default=19, help='how many vigilance images needed for one block')
    parser.add_argument('--min_dist_targets', type=int, default=35, help='minimum distance (difference in index) between '
                                                                         'first and second presentation of a target')
    parser.add_argument('--max_dist_targets', type=int, default=140, help='maximum distance (difference in index) between '
                                                                          'first and second presentation of a target')
    parser.add_argument('--min_dist_vigs', type=int, default=1, help='min distance (difference in index) between '
                                                                     'first and second presentation of a vigilance '
                                                                     'image')
    parser.add_argument('--max_dist_vigs', type=int, default=4, help='maximum distance (difference in index) between '
                                                                     'first and second presentation of a vigilance '
                                                                     'image')
    parser.add_argument('--num_workers', type=int, default=10, help='number of tracks to construct')
    parser.add_argument('--num_blocks', type=int, default=-1, help='number of sequences (i.e., blocks) per worker, -1 for '
                                                                   'the maximum available')
    parser.add_argument('--clustering', type=bool, default=False, help='whether stimuli are clustered into sets of which '
                                                                      'only member can be in a given track')
    parser.add_argument('--preview', type=bool, default=False, help='set to true when generating a sequence for the '
                                                                    'mturk preview. Will make sure it is saved with '
                                                                    'the proper filename')

    args = parser.parse_args()

# %% Setting up -------------------------------------------------------------------------------------------------------

    if not os.path.exists(args.track_dir):
        os.makedirs(args.track_dir)

    target_dir_full = os.path.join(args.image_root, args.target_dir)
    filler_dir_full = os.path.join(args.image_root, args.filler_dir)

    targets_all = os.listdir(target_dir_full)  # list of all (clusters) of targets

    if target_dir_full == filler_dir_full:
        separate_fillers = False  # we will be sampling the fillers from the same pool of images as the targets
        max_num_blocks = int(math.floor(len(targets_all) / (args.num_targets + args.num_fillers + args.num_vigs)))

    else:
        separate_fillers = True  # we will be sampling the fillers from a different pool of images
        fillers_all = os.listdir(filler_dir_full)  # list of all (clusters of) fillers
        max_num_blocks = min(math.floor(len(targets_all) / args.num_targets),
                             math.floor(len(fillers_all) / (args.num_fillers + args.num_vigs)))

    if args.num_blocks == -1:
        num_blocks = max_num_blocks
    elif args.num_blocks > max_num_blocks:
        Warning("You have asked for more blocks than the number of stimuli allow. Only ",
                max_num_blocks, " will be constructed")
        num_blocks = max_num_blocks
    else:
        num_blocks = args.num_blocks

    if args.preview:
        args.num_workers = 1 # we only need one sequence for the mturk preview

# %% Creating worker sequences -----------------------------------------------------------------------------------------

    for worker in range(args.num_workers):

        # region Selecting images
        # ------------------------
        # Reset
        targets_available = copy.deepcopy(targets_all)
        if separate_fillers:
            fillers_available = copy.deepcopy(fillers_all)
        else:
            fillers_available = targets_available  # pointing to the same list

        # Sample and remove
        targets_selected = \
            [targets_available.pop(random.randrange(len(targets_available))) for _ in range(num_blocks * args.num_targets)]

        fillers_selected = \
            [fillers_available.pop(random.randrange(len(fillers_available))) for _ in range(num_blocks * args.num_fillers)]

        vigs_selected = \
            [fillers_available.pop(random.randrange(len(fillers_available))) for _ in range(num_blocks * args.num_vigs)]

        # Add parent dir
        targets_selected = [os.path.join(args.target_dir, x) for x in targets_selected]
        fillers_selected = [os.path.join(args.filler_dir, x) for x in fillers_selected]
        vigs_selected = [os.path.join(args.filler_dir, x) for x in vigs_selected]

        # Select one member of each set (subdir)
        if args.clustering:
            targets_selected = [os.path.join(x, random.sample(os.listdir(x), 1)[0]) for x in targets_selected]
            fillers_selected = [os.path.join(x, random.sample(os.listdir(x), 1)[0]) for x in fillers_selected]
            vigs_selected = [os.path.join(x, random.sample(os.listdir(x), 1)[0]) for x in vigs_selected]

        # Chunk the lists in num_blocks chunks
        targets_selected = [targets_selected[x:x + args.num_targets] for x in
                            range(0, len(targets_selected), args.num_targets)]
        fillers_selected = [fillers_selected[x:x + args.num_fillers] for x in
                            range(0, len(fillers_selected), args.num_fillers)]
        vigs_selected = [vigs_selected[x:x + args.num_vigs] for x in range(0, len(vigs_selected), args.num_vigs)]

        # Add everything together such that each chunk has all the images for one block in it
        # images_selected = [targets_selected[i] + vigs_selected[i] + fillers_selected[i] for i in range(num_blocks)]
        images_selected = [{"targets": targets_selected[i],
                            "fillers": fillers_selected[i],
                            "vigs": vigs_selected[i]} for i in range(num_blocks)]
        # endregion

        # region Create sequence
        # ----------------------
        # Reorder the images in one track of num_blocks valid sequences
        track = []  # list of sequences (blocks) for one worker
        types = []  # describes trial types (e.g., "target repeat")

        for sequence_i in range(len(images_selected)):
            sequence_current, types_current = create_sequence(images_selected[sequence_i], args.min_dist_targets,
                                                              args.max_dist_targets, args.min_dist_vigs, args.max_dist_vigs)
            track.append(sequence_current)
            types.append(types_current)

        # endregion

        # region Safety checks
        # ---------------------
        # Track level checks
        approved, text = check_track(images_selected, track, types)

        if not approved:
            raise Exception(text)

        # Track level checks for stimulus clusters (e.g., to avoid multiple members of the same cluster in one track)
        if args.clustering:
            clusters_selected = \
                [dict(zip(x.keys(), [[os.path.dirname(z) for z in y] for y in x.values()])) for x in images_selected]

            approved, text = check_track(clusters_selected,
                                         [[os.path.dirname(y) for y in x] for x in track],
                                         types)
            if not approved:
                raise Exception(text + " (for clusters)")

        # endregion

        # region Save output
        # ---------------------
        # Track level checks

        # Saving everything to json file
        if not args.preview:
            with open(os.path.join(args.track_dir, "track_" + str(worker).zfill(5)) + ".json", 'w') as fp:
                json.dump({"sequences": track, "types": types}, fp)
        else:
            with open(os.path.join(args.track_dir, "previewSequence.json"), 'w') as fp:
                json.dump({"sequences": track, "types": types}, fp)

        print(worker)
        # endregion
