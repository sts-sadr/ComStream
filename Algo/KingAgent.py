from .Singelton import Singleton
from .DataAgent import DataAgent
from .Agent import Agent
from .Utils import get_distance_tf_idf_cosine, get_seconds
import random
import re
import time


@Singleton
class KingAgent:
    prev_residual = 0

    def __init__(self, max_topic_count,
                 communication_step: str,
                 clean_up_step: str,
                 radius: float,
                 alpha: int,
                 outlier_threshold: float,
                 top_n: int,
                 dp_count: int,
                 fading_rate,
                 generic_distance=get_distance_tf_idf_cosine):

        pattern = re.compile(r'^[0-9]+:[0-9]{2}:[0-9]{2}$')
        are_invalid_steps = len(pattern.findall(communication_step)) != 1 or len(pattern.findall(clean_up_step)) != 1

        if are_invalid_steps:
            raise Exception(f'Invalid inputs fot steps')

        self.agents = {}
        self.radius = radius
        self.fading_rate = fading_rate
        self.communication_step = communication_step
        self.alpha = alpha
        self.max_topic_count = max_topic_count
        self.outlier_threshold = outlier_threshold
        self.top_n = top_n
        self.clean_up_deltatime = clean_up_step
        self.data_agent = DataAgent(count=dp_count)
        self.generic_distance_function = generic_distance

    def create_agent(self) -> int:
        agent = Agent(self, generic_distance_function=self.generic_distance_function)
        self.agents[agent.agent_id] = agent
        return agent.agent_id

    def remove_agent(self, agent_id) -> None:
        for dp_id in self.agents[agent_id].dp_ids:
            self.agents[agent_id].remove_data_point(dp_id)
        del self.agents[agent_id]

    def handle_outliers(self) -> None:
        outliers_id = []
        for agent_id, agent in self.agents.items():
            outliers_id.extend(agent.get_outliers())
        outliers_to_join = []
        for outlier_id in outliers_id:
            min_distance = float('infinity')
            similar_agent_id = -1
            for agent_id, agent in self.agents.items():
                distance = agent.get_distance(self.data_agent, self.data_agent.data_points[outlier_id].tf)
                if distance <= min_distance:
                    min_distance = distance
                    similar_agent_id = agent_id
            if similar_agent_id != -1:
                outliers_to_join.append((outlier_id, min_distance, similar_agent_id))
            else:
                print('Sth went wrong!')
        outliers_to_join = sorted(outliers_to_join, key=lambda tup: tup[1])
        outliers_to_join = outliers_to_join[:self.top_n]

        for dp_id, distance, agent_id in outliers_to_join:
            if distance > self.radius:
                new_agent_id = self.create_agent()
                self.agents[new_agent_id].add_data_point(self.data_agent.data_points[dp_id])
            else:
                self.agents[agent_id].add_data_point(self.data_agent.data_points[dp_id])

    def warm_up(self):
        for i in range(self.max_topic_count):
            self.create_agent()

        agents_dict = {id_: self.alpha for id_ in self.agents.keys()}
        for i in range(self.max_topic_count * self.alpha):
            random_agent_id = random.sample(list(agents_dict))
            dp = self.data_agent.get_next_dp()
            self.agents[random_agent_id].add_data_point(dp)
            agents_dict[random_agent_id] -= 1
            if agents_dict[random_agent_id] == 0:
                del agents_dict[random_agent_id]
        del agents_dict

    def stream(self):
        dp = self.data_agent.get_next_dp()
        min_distance = float('infinity')
        similar_agent_id = -1
        for agent_id, agent in self.agents.items():
            distance = agent.get_distance(self.data_agent, self.data_agent.data_points[dp.dp_id].tf)
            if distance <= min_distance:
                min_distance = distance
                similar_agent_id = agent_id
        if min_distance > self.radius:
            new_agent_id = self.create_agent()
            self.agents[new_agent_id].add_data_point(self.data_agent.data_points[dp.dp_id])
        else:
            self.agents[similar_agent_id].add_data_point(self.data_agent.data_points[dp.dp_id])

    def fade_agents(self):
        for agent_id, agent in self.agents.items():
            agent.fade_agent(self.fading_rate)
            if agent.weight < self.data_agent.epsilon:
                self.remove_agent(agent_id)

    def handle_old_dps(self):
        for agent_id, agent in self.agents.items():
            agent.handle_old_dps()

    def train(self):
        self.warm_up()
        self.handle_outliers()

        while self.data_agent.has_next_dp():

            self.stream()

            residual = time.mktime(DataAgent.date.timetuple()) % get_seconds(self.communication_step)
            if residual < KingAgent.prev_residual:
                KingAgent.prev_residual = 0
                self.handle_old_dps()
                self.handle_outliers()
                self.fade_agents()
            KingAgent.prev_residual = residual
