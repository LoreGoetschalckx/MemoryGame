from flask import Flask, request
from flask_restful import Resource, Api
from flask_cors import CORS

import os
import json
import pandas as pd
import datetime
import time
from filelock import Timeout, FileLock

app = Flask(__name__)
api = Api(app)
CORS(app)
with open("server_config.json") as f:
    config = json.load(f)

lock_assigned_sequences = FileLock(config["assignedSequencesFile"] + ".lock")
lock_data = FileLock(config["dataFile"] + ".lock")
lock_data_sandbox = FileLock(config["dataSandboxFile"] + ".lock")
lock_when_to_stop = FileLock(config["dashboardFile"] + ".lock")
lock_submission_file = FileLock(config["submitFile"] + ".lock")

class InitializePreview(Resource):
    def initialize_vars(self):
        self.trial_feedback = request.args.get("trialFeedback")
        self.timestamp = datetime.datetime.now()

    def get_sequence_info(self, feedback):
        assigned_file = config["previewSequenceFile"]
        with open(assigned_file) as f:
            sequence_info = json.load(f)
        index_to_run = 0

        run_info = {"index_to_run": index_to_run,
                    "sequenceFile": assigned_file,
                    "images": sequence_info["sequences"][index_to_run],
                    "blocked": int(False),
                    "finished": int(False),
                    "timestamp": self.timestamp.__str__()}

        # only send correct answers along if you will be giving trial feedback (less risk of tech savvy workers using
        # it to get perfect scores
        if feedback:
            run_info["conditions"] = sequence_info["types"][run_info["index_to_run"]]

        return run_info

    def get(self):
        self.initialize_vars()
        return_dict = self.get_sequence_info(self.trial_feedback)
        return_dict["running"] = False
        return return_dict


class InitializeRun(Resource):
    def initialize_vars(self):
        self.workerId = request.args.get("workerId")
        self.medium = request.args.get("medium")
        self.trial_feedback = request.args.get("trialFeedback")
        self.assigned_sequences_df = pd.read_csv(config["assignedSequencesFile"], delimiter=",")
        self.assigned_sequences_df = self.assigned_sequences_df.set_index("workerId", drop=False)
        self.timestamp = datetime.datetime.now()

    def available_sequences(self):
        sequence_files = os.listdir(os.path.join(config["sequenceDir"]))
        assigned_files = self.assigned_sequences_df["sequenceFile"].values.tolist()
        assigned_files = [os.path.basename(x) for x in assigned_files]
        available_files = [x for x in sequence_files if x not in assigned_files and x.endswith(".json")]
        available_files = [x for x in available_files if not os.path.samefile(os.path.join(config["sequenceDir"],x), config["previewSequenceFile"])]
        available_files = sorted(available_files)
        return available_files

    def assign_new_sequence(self, workerId):
        if workerId in self.assigned_sequences_df["workerId"].values:
            raise Exception('cannot assign new sequence, workerId already has one')
        else:
            available_files = self.available_sequences()
            assigned_file = os.path.join(config["sequenceDir"], available_files[0])
            new_row = {"workerId": workerId,
                       "sequenceFile": assigned_file,
                       "indexToRun": int(0),
                       "blocked": False,
                       "finished": False,
                       "timestamp": self.timestamp.__str__(),
                       "version": config["version"]}

            self.assigned_sequences_df = self.assigned_sequences_df.append(pd.DataFrame(new_row, index=[0]),
                                                                           ignore_index=True)
            self.assigned_sequences_df = self.assigned_sequences_df.set_index("workerId", drop=False)

    def already_running(self, workerId, timestamp, new_worker):
        if new_worker:
            return False
        else:
            # if previous initialization was less than 5 minutes ago, session is probably still active
            previous_timestamp = self.assigned_sequences_df.loc[workerId, "timestamp"]
            previous_timestamp = datetime.datetime.strptime(previous_timestamp.__str__(), "%Y-%m-%d %H:%M:%S.%f")
            return (timestamp - previous_timestamp) < datetime.timedelta(minutes=4)

    def get_sequence_info(self, workerId, feedback):
        assigned_file = self.assigned_sequences_df.loc[workerId, "sequenceFile"]
        with open(assigned_file) as f:
            sequence_info = json.load(f)
        index_to_run = int(self.assigned_sequences_df.loc[workerId, "indexToRun"])

        run_info = {"index_to_run": index_to_run,
                    "sequenceFile": str(self.assigned_sequences_df.loc[workerId, "sequenceFile"]),
                    "images": sequence_info["sequences"][index_to_run],
                    "blocked": int(self.assigned_sequences_df.loc[workerId, "blocked"]),
                    "finished": int(self.assigned_sequences_df.loc[workerId, "finished"]),
                    "maintenance": config["maintenance"],
                    "timestamp": self.timestamp.__str__()}

        # only send correct answers along if you will be giving trial feedback (less risk of tech savvy workers using
        # it to get perfect scores
        if feedback:
            run_info["conditions"] = sequence_info["types"][run_info["index_to_run"]]

        return run_info

    def update_df(self, run_info):
        if not (run_info["running"] or run_info["finished"] or run_info["blocked"] or run_info["maintenance"]):
            if run_info["index_to_run"] + 1 >= config["maxNumRuns"]:
                self.assigned_sequences_df.at[self.workerId, "finished"] = True
            else:
                self.assigned_sequences_df.at[self.workerId, "indexToRun"] = run_info["index_to_run"] + 1
            self.assigned_sequences_df.at[self.workerId, "timestamp"] = self.timestamp.__str__()
            self.assigned_sequences_df.to_csv(config["assignedSequencesFile"], index=False)

    def get(self):
        with lock_assigned_sequences:
            self.initialize_vars()

            # assign sequence file if worker is new
            if self.workerId not in self.assigned_sequences_df["workerId"].values:
                new_worker = True
                self.assign_new_sequence(self.workerId)
            else:
                new_worker = False

            # get assigned sequence info
            return_dict = self.get_sequence_info(self.workerId, self.trial_feedback)

            # check if another run might be active
            return_dict["running"] = self.already_running(self.workerId, self.timestamp, new_worker)

            # update the database
            self.update_df(return_dict)

            return return_dict


class FinalizeRun(Resource):
    def initialize_vars(self):
        start = time.time()
        self.data_received = request.get_json()
        self.medium = self.data_received["medium"]
        self.sequence_info = self.get_sequence_info(self.data_received["sequenceFile"])
        self.return_dict = \
            {"blocked": False,  # initializing, will be set to True if blocked,
             "finished": self.data_received["indexToRun"] + 1 >= config["maxNumRuns"],
             "maintenance": config["maintenance"]}
        end = time.time()
        print("initialized vars, took ", end - start, " seconds")

    def get_sequence_info(self, sequence_file):
        with open(sequence_file) as f:
            sequence_info = json.load(f)
        return sequence_info

    def update_data_file(self):
        start = time.time()
        data_received = self.data_received
        sequence_info = self.sequence_info
        run_index = data_received["indexToRun"]
        num_trials = data_received["numTrials"]
        meta_data = {
            "medium": data_received["medium"],
            "sequenceFile": data_received["sequenceFile"],
            "workerId": data_received["workerId"],
            "assignmentId": data_received["assignmentId"],
            "timestamp": data_received["timestamp"],
            "runIndex": run_index,
            "initTime": data_received["initTime"],
            "finishTime": data_received["finishTime"]
        }

        # Setting data file and lock
        if self.medium == "mturk_sandbox":
            data_file = config["dataSandboxFile"]
            lock = lock_data_sandbox
        else:
            data_file = config["dataFile"]
            lock = lock_data

        print(lock)

        with lock:
            data_all = pd.read_csv(data_file)

            # Trial data
            data = {
                "response": [1 if i in data_received["responseIndices"] else 0 for i in range(num_trials)],
                "trialIndex": list(range(data_received["numTrials"])),
                "condition": sequence_info["types"][run_index][0:num_trials],
                "image": sequence_info["sequences"][run_index][0:num_trials]
            }
            df = pd.DataFrame.from_dict(data, orient='index').transpose()
            df = pd.concat([df, pd.DataFrame([meta_data] * num_trials)], axis=1)
            data_all = data_all.append(df, ignore_index=True)
            data_all.to_csv(data_file, index=False)

        end = time.time()
        print("updated data df, took ", end - start, " seconds")

    def compute_scores(self):
        start = time.time()
        data_received = self.data_received
        sequence_info = self.sequence_info
        run_index = data_received["indexToRun"]
        num_trials = data_received["numTrials"]

        repeat_indices = []
        for i in range(num_trials):
            if sequence_info["types"][run_index][i] in config["conditionLabels"]["repeatTrials"]:
                repeat_indices.append(i)
        no_repeat_indices = []
        for i in range(num_trials):
            if sequence_info["types"][run_index][i] in config["conditionLabels"]["noRepeatTrials"]:
                no_repeat_indices.append(i)

        hits = set(repeat_indices) & set(data_received["responseIndices"])
        false_alarms = set(no_repeat_indices) & set(data_received["responseIndices"])

        end = time.time()
        print("computed scores, took ", end - start, " seconds")
        return {"hit_rate": float(len(hits)) / len(repeat_indices) if len(repeat_indices) > 0 else -1,
                "false_alarm_num": len(false_alarms)}

    def evaluate_vigilance(self, vig_hr_criterion, far_criterion):
        start = time.time()
        # initializing
        data_received = self.data_received
        sequence_info = self.sequence_info
        run_index = data_received["indexToRun"]
        num_trials = data_received["numTrials"]
        passing_criteria = True

        vig_repeat_indices = [i for i in range(num_trials) if sequence_info["types"][run_index][i] == "vig repeat"]
        no_repeat_indices = [i for i in range(num_trials) if sequence_info["types"][run_index][i] in ["filler",
                                                                                                      "target",
                                                                                                      "vig"]]
        print(vig_repeat_indices)
        print(no_repeat_indices)

        if len(vig_repeat_indices) > 0:
            vig_hits = set(vig_repeat_indices) & set(data_received["responseIndices"])
            vig_hit_rate = float(len(vig_hits)) / len(vig_repeat_indices)
            if vig_hit_rate < vig_hr_criterion:
                passing_criteria = False

        false_alarms = set(no_repeat_indices) & set(data_received["responseIndices"])
        false_alarm_rate = float(len(false_alarms))/len(no_repeat_indices)
        if false_alarm_rate >= far_criterion:
            passing_criteria = False

        end = time.time()
        print("evaluated vigilance, took ", end - start, " seconds")
        return "pass" if passing_criteria else "fail"

    def block_worker(self, workerId):
        start = time.time()
        print("blocking")
        self.return_dict["blocked"] = True

        with lock_assigned_sequences:
            assigned_sequences_df = pd.read_csv(config["assignedSequencesFile"], delimiter=",")
            assigned_sequences_df = assigned_sequences_df.set_index("workerId", drop=False)
            assigned_sequences_df.at[workerId, "blocked"] = True
            assigned_sequences_df.to_csv(config["assignedSequencesFile"], index=False)

        end = time.time()
        print("blocked worker, took ", end - start, " seconds")

    def update_dashboard(self, valid):
        start = time.time()
        with lock_when_to_stop:
            with open(config["dashboardFile"]) as f:
                dashboard = json.load(f)
            dashboard["numBlocksTotalSoFar"] += 1
            dashboard["numValidBlocksSoFar"] += valid
            with open(config["dashboardFile"], 'w') as fp:
                json.dump(dashboard, fp)

        end = time.time()
        print("updated when to stop, took ", end - start, " seconds")

    def post(self):
        self.initialize_vars()
        if not self.data_received['preview']:
            self.update_data_file()
            valid = 0

            # Check vigilance performance and block if necessary
            if self.data_received['workerId'] not in config["whitelistWorkerIds"]:
                if self.evaluate_vigilance(config["blockingCriteria"]["vigHrCriterion"],
                                           config["blockingCriteria"]["farCriterion"]) == "fail":
                    self.block_worker(self.data_received["workerId"])
                else:
                    valid = 1
            else:
                valid = 1

            self.update_dashboard(valid)

        # Add scores to return_dict
        self.return_dict.update(self.compute_scores())

        return self.return_dict

class SubmitRuns(Resource):
    def initialize_vars(self):
        self.data_received = request.get_json()

    def update_submissions(self):
        data = self.data_received
        with lock_submission_file:
            submitted_runs_df = pd.read_csv(config["submitFile"])
            submitted_runs_df = submitted_runs_df.append(data, ignore_index=True)
            submitted_runs_df.to_csv(config["submitFile"], index=False)

    def post(self):
        self.initialize_vars()
        self.update_submissions()
        return ("submission successful")


api.add_resource(InitializePreview, '/initializepreview')
api.add_resource(InitializeRun, '/initializerun')
api.add_resource(FinalizeRun, '/finalizerun')
api.add_resource(SubmitRuns, '/submitruns')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config["port"], debug=True)
