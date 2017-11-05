import numpy as np

from mushroom.algorithms.agent import Agent
from mushroom.approximators.regressor import Ensemble, Regressor
from mushroom.utils.replay_memory import Buffer, ReplayMemory


class DQN(Agent):
    """
    Deep Q-Network algorithm.
    "Human-Level Control Through Deep Reinforcement Learning".
    Mnih V. et al.. 2015.

    """
    def __init__(self, approximator, policy, gamma, params):
        self.__name__ = 'DQN'

        alg_params = params['algorithm_params']
        self._batch_size = alg_params.get('batch_size')
        self._n_approximators = alg_params.get('n_approximators', 1)
        self._clip_reward = alg_params.get('clip_reward', True)
        self._train_frequency = alg_params.get('train_frequency')
        self._target_update_frequency = alg_params.get(
            'target_update_frequency')
        self._max_no_op_actions = alg_params.get('max_no_op_actions', 0)
        self._no_op_action_value = alg_params.get('no_op_action_value', 0)

        self._replay_memory = ReplayMemory(alg_params.get('max_replay_size'),
                                           alg_params.get('history_length', 1))
        self._buffer = Buffer(size=alg_params.get('history_length', 1))

        self._n_updates = 0
        self._episode_steps = 0
        self._no_op_actions = None

        apprx_params_train = params['approximator_params']
        apprx_params_train['params']['name'] = 'train'
        apprx_params_target = params['approximator_params']
        apprx_params_target['params']['name'] = 'target'
        self.approximator = Regressor(approximator, **apprx_params_train)
        self.target_approximator = Regressor(approximator,
                                             n_models=self._n_approximators,
                                             **apprx_params_target)
        policy.set_q(self.approximator)

        if self._n_approximators == 1:
            self.target_approximator.model.set_weights(
                self.approximator.model.get_weights())
        else:
            for i in xrange(self._n_approximators):
                self.target_approximator.model[i].set_weights(
                    self.approximator.model.get_weights())

        super(DQN, self).__init__(policy, gamma, params)

    def fit(self, dataset, n_iterations=1):
        """
        Single fit step.

        Args:
            dataset (list): the dataset;
            n_iterations (int, 1): number of fit steps of the approximator.

        """
        self._replay_memory.add(dataset)
        if n_iterations == 0:
            pass
        else:
            assert n_iterations == 1

            state, action, reward, next_state, absorbing, _ =\
                self._replay_memory.get(self._batch_size)

            if self._clip_reward:
                reward = np.clip(reward, -1, 1)

            q_next = self._next_q(next_state, absorbing)
            q = reward + self._gamma * q_next

            self.approximator.fit(state, action, q, **self.params['fit_params'])

            self._n_updates += 1

            self._update_target()

    def _update_target(self):
        """
        Update the target network if the conditions on the number of updates
        are met.

        """
        if self._n_updates % self._target_update_frequency == 0:
            self.target_approximator.model.set_weights(
                self.approximator.model.get_weights())

    def _next_q(self, next_state, absorbing):
        """
        Args:
            next_state (np.array): the states where next action has to be
                evaluated;
            absorbing (np.array): the absorbing flag for the states in
                `next_state`.

        Returns:
            Maximum action-value for each state in `next_states`.

        """
        q = self.target_approximator.predict(next_state)
        if np.any(absorbing):
            q *= 1 - absorbing.reshape(-1, 1)

        return np.max(q, axis=1)

    def initialize(self, mdp_info):
        """
        Initialize `mdp_info` attribute.

        Args:
            mdp_info (dict): information about the mdp (e.g. discount factor).

        """
        super(DQN, self).initialize(mdp_info)

        self._replay_memory.initialize(self.mdp_info)

    def draw_action(self, state):
        self._buffer.add(state)

        if self._episode_steps < self._no_op_actions:
            action = np.array([self._no_op_action_value])
            self.policy.update()
        else:
            extended_state = self._buffer.get()

            action = super(DQN, self).draw_action(extended_state)

        self._episode_steps += 1

        return action

    def episode_start(self):
        self._no_op_actions = np.random.randint(
            self._buffer.size, self._max_no_op_actions + 1)
        self._episode_steps = 0

    def __str__(self):
        return self.__name__


class DoubleDQN(DQN):
    """
    Double DQN algorithm.
    "Deep Reinforcement Learning with Double Q-Learning".
    Hasselt H. V. et al.. 2016.

    """
    def __init__(self, approximator, policy, gamma, params):
        self.__name__ = 'DoubleDQN'

        super(DoubleDQN, self).__init__(approximator, policy, gamma, params)

    def _next_q(self, next_state, absorbing):
        q = self.approximator.predict(next_state)
        if np.any(absorbing):
            q *= 1 - absorbing.reshape(-1, 1)
        max_a = np.argmax(q, axis=1)

        return self.target_approximator.predict(next_state, max_a)


class AveragedDQN(DQN):
    """
    Averaged-DQN algorithm.
    "Averaged-DQN: Variance Reduction and Stabilization for Deep Reinforcement
    Learning". Anschel O. et al.. 2017.

    """
    def __init__(self, approximator, policy, gamma, params):
        self.__name__ = 'AveragedDQN'

        super(AveragedDQN, self).__init__(approximator, policy, gamma, params)

        self._n_fitted_target_models = 1

        assert isinstance(self.target_approximator.model, Ensemble)

    def _update_target(self):
        if self._n_updates % self._target_update_frequency == 0:
            idx = self._n_updates / self._target_update_frequency\
                  % self._n_approximators
            self.target_approximator.model[idx].set_weights(
                self.approximator.model.get_weights())

            if self._n_fitted_target_models < self._n_approximators:
                self._n_fitted_target_models += 1

    def _next_q(self, next_state, absorbing):
        q = list()
        for idx in xrange(self._n_fitted_target_models):
            q.append(self.target_approximator.predict(next_state, idx=idx))
        q = np.mean(q, axis=0)
        if np.any(absorbing):
            q *= 1 - absorbing.reshape(-1, 1)

        return np.max(q, axis=1)


class WeightedDQN(AveragedDQN):
    """
    ...

    """
    def __init__(self, approximator, policy, gamma, params):
        self.__name__ = 'WeightedDQN'

        super(WeightedDQN, self).__init__(approximator, policy, gamma, params)

    def _next_q(self, next_state, absorbing):
        samples = np.ones((self._n_fitted_target_models,
                           next_state.shape[0],
                           self.mdp_info['action_space'].n))
        for i in xrange(self._n_fitted_target_models):
            samples[i] = self.target_approximator.predict(next_state,
                                                          idx=i)
        W = np.zeros(next_state.shape[0])
        for i in xrange(next_state.shape[0]):
            means = np.mean(samples[:, i, :], axis=0)
            max_idx = np.argmax(samples[:, i, :], axis=1)
            max_idx, max_count = np.unique(max_idx, return_counts=True)
            count = np.zeros(self.mdp_info['action_space'].n)
            count[max_idx] = max_count
            w = count / float(self._n_fitted_target_models)
            W[i] = np.dot(w, means)

        if np.any(absorbing):
            W *= 1 - absorbing

        return W