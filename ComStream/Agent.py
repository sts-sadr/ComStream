from typing import Callable

from ComStream.Utils import get_seconds


class Agent:
    agent_id = 0
    epsilon = 1e-7

    def __init__(self, king_agent, generic_distance_function: Callable):
        """
        the object of agent where the properties of the agent are kept
        :param king_agent: the object of the KingAgent so we have access to global variables
        :param generic_distance_function: the distance function we want to use
        :return: None
        """
        self.agent_id = Agent.agent_id
        self.outlier_threshold = king_agent.outlier_threshold
        Agent.agent_id += 1
        self.agent_frequencies = {}
        self.weight = 0
        self.dp_ids = []
        self.king_agent = king_agent
        self.generic_distance_function = generic_distance_function

    def add_data_point(self, dp) -> None:
        """
        adding dp to the agent
        :param dp: dp we want to add to the agent
        :return: None
        """
        self.weight += 1
        for token_id, frequency in dp.freq.items():
            if token_id in self.agent_frequencies:
                self.agent_frequencies[token_id] += frequency
                self.update_global_tf(frequency, token_id)
            else:
                self.king_agent.global_idf_count[token_id] = self.king_agent.global_idf_count.get(token_id, 0) + 1
                self.agent_frequencies[token_id] = frequency
                self.update_global_tf(frequency, token_id)

        self.dp_ids.append(dp.dp_id)
        self.king_agent.dp_id_to_agent_id[dp.dp_id] = self.agent_id

    def update_global_tf(self, frequency, token_id):
        """
        update the global term frequencies when adding a new data point
        :param frequency: the amount added
        :param token_id: the id of the word added
        :return: None
        """
        if token_id in self.king_agent.data_agent.global_freq:
            self.king_agent.data_agent.global_freq[token_id] += frequency
            self.king_agent.data_agent.terms_global_frequency += frequency
        else:
            self.king_agent.data_agent.global_freq[token_id] = frequency
            self.king_agent.data_agent.terms_global_frequency += frequency

    def remove_data_point(self, dp_id: int, outlier=False) -> None:
        """
        removing data point from agent
        :param dp_id: dp id
        :param outlier : Boolean
        :return: None
        """
        try:
            self.dp_ids.remove(dp_id)
            if self.weight <= 0:
                self.weight = 0
            for token_id, frequency in self.king_agent.data_agent.data_points[dp_id].freq.items():
                if token_id in self.agent_frequencies:
                    self.agent_frequencies[token_id] -= frequency

                    if self.agent_frequencies[token_id] <= 0:
                        del self.agent_frequencies[token_id]
                        self.king_agent.global_idf_count[token_id] -= 1
                        if self.king_agent.global_idf_count[token_id] == 0:
                            del self.king_agent.global_idf_count[token_id]
                    self.king_agent.data_agent.global_freq[token_id] -= frequency
                    self.king_agent.data_agent.terms_global_frequency -= frequency
                else:
                    self.king_agent.data_agent.global_freq[token_id] -= frequency
                    self.king_agent.data_agent.terms_global_frequency -= frequency

            if not outlier:
                del self.king_agent.data_agent.data_points[dp_id]
            del self.king_agent.dp_id_to_agent_id[dp_id]

        except ValueError:
            print(f'There is no such data point in Agent : {dp_id}')

    def fade_agent_weight(self, fade_rate: float, delete_faded_threshold: float) -> None:
        """
        fade an agent's weight
        :param fade_rate: the amount to be faded
        :param delete_faded_threshold: delete the agent if it's weight gets less than this threshold
        :return: None
        """
        if abs(fade_rate) < 1e-9:
            pass
        else:
            if fade_rate > 1 or fade_rate < 0 or delete_faded_threshold > 1 or delete_faded_threshold < 0:
                message = f'Invalid Fade Rate or delete_agent_weight_threshold : {fade_rate, delete_faded_threshold}'
                raise Exception(message)
            else:
                self.weight = self.weight * (1 - fade_rate)
                if self.weight < delete_faded_threshold:
                    self.king_agent.remove_agent(self.agent_id)

    def get_outliers(self, out) -> None:
        """
        getting outliers of agent
        :return: list of ids of outliers
        """
        outliers_id = []
        for dp_id in self.dp_ids:
            dp = self.king_agent.data_agent.data_points[dp_id]
            distance = self.get_distance(self.king_agent, dp.freq)
            if distance > self.outlier_threshold:
                self.remove_data_point(dp_id, outlier=True)
                outliers_id.append(dp_id)
        out.extend(outliers_id)

    def get_distance(self, king_agent, f: dict):
        """
        calls the function that finds the distance
        :param king_agent: the object of KingAgent
        :param f: a dictionary of term frequencies {token_id:frequency} of the dp
        :return: (int) returns the distance of the dp and this agent
        """
        return self.generic_distance_function(king_agent, f, self.agent_frequencies)

    def handle_old_dps(self):
        """
        deletes the dps that are older than sliding_window_interval time interval
        :return: None
        """
        for dp_id in self.dp_ids:
            dp = self.king_agent.data_agent.data_points[dp_id]
            if abs((dp.created_at - self.king_agent.current_date).total_seconds()) > get_seconds(
                    self.king_agent.sliding_window_interval):
                self.remove_data_point(dp_id)
