import os
import numpy as np
import tensorflow as tf
from logging import getLogger

logger = getLogger(__name__)

class Statistic(object):
  def __init__(self, sess, t_test, t_learn_start, model_dir, variables, max_to_keep=20):
    self.sess = sess
    self.t_test = t_test
    self.t_learn_start = t_learn_start

    self.reset()
    self.max_avg_ep_reward = 0

    with tf.variable_scope('t'):
      self.t_op = tf.Variable(0, trainable=False, name='t')
      self.t_add_op = self.t_op.assign_add(1)

    self.model_dir = model_dir
    self.saver = tf.train.Saver(variables + [self.t_op], max_to_keep=max_to_keep)
    self.writer = tf.train.SummaryWriter('./logs/%s' % self.model_dir, self.sess.graph)

    with tf.variable_scope('summary'):
      scalar_summary_tags = [
        'average/reward', 'average/loss', 'average/q', 'average/v', 'average/a',
        'episode/max reward', 'episode/min reward', 'episode/avg reward',
      ]

      self.summary_placeholders = {}
      self.summary_ops = {}

      for tag in scalar_summary_tags:
        self.summary_placeholders[tag] = tf.placeholder('float32', None, name=tag.replace(' ', '_'))
        self.summary_ops[tag]  = tf.scalar_summary(tag, self.summary_placeholders[tag])

      histogram_summary_tags = ['episode/rewards']

      for tag in histogram_summary_tags:
        self.summary_placeholders[tag] = tf.placeholder('float32', None, name=tag.replace(' ', '_'))
        self.summary_ops[tag]  = tf.histogram_summary(tag, self.summary_placeholders[tag])

  def reset(self):
    self.num_game = 0
    self.update_count = 0
    self.ep_reward = 0.
    self.total_loss = 0.
    self.total_reward = 0.
    self.actions = []
    self.total_q = []
    self.total_v = []
    self.total_a = []
    self.ep_rewards = []

  def on_step(self, action, reward, terminal, q, v, a, loss, is_update):
    self.t = self.t_add_op.eval(session=self.sess)

    if self.t >= self.t_learn_start:
      self.total_q.extend(q)
      self.total_v.extend(v)
      self.total_a.extend(a)
      self.actions.append(action)

      self.total_loss += loss
      self.total_reward += reward

      if terminal:
        self.num_game += 1
        self.ep_rewards.append(self.ep_reward)
        self.ep_reward = 0.
      else:
        self.ep_reward += reward

      if is_update:
        self.update_count += 1

      if self.t % self.t_test == self.t_test - 1 and self.update_count != 0:
        avg_q = np.mean(self.total_q)
        avg_v = np.mean(self.total_v)
        avg_a = np.mean(self.total_a)
        avg_loss = self.total_loss / self.update_count
        avg_reward = self.total_reward / self.t_test

        try:
          max_ep_reward = np.max(self.ep_rewards)
          min_ep_reward = np.min(self.ep_rewards)
          avg_ep_reward = np.mean(self.ep_rewards)
        except:
          max_ep_reward, min_ep_reward, avg_ep_reward = 0, 0, 0

        logger.info('\navg_r: %.4f, avg_l: %.6f, avg_q: %3.6f, avg_ep_r: %.4f, max_ep_r: %.4f, min_ep_r: %.4f, # game: %d' \
            % (avg_reward, avg_loss, avg_q, avg_ep_reward, max_ep_reward, min_ep_reward, self.num_game))

        if self.max_avg_ep_reward * 0.9 <= avg_ep_reward:
          self.save_model(self.t)
          self.max_avg_ep_reward = max(self.max_avg_ep_reward, avg_ep_reward)

        self.inject_summary({
            # scalar
            'average/q': avg_q,
            'average/v': avg_v,
            'average/a': avg_a,
            'average/loss': avg_loss,
            'average/reward': avg_reward,
            'episode/max reward': max_ep_reward,
            'episode/min reward': min_ep_reward,
            'episode/avg reward': avg_ep_reward,
            # histogram
            'episode/rewards': self.ep_rewards,
          }, self.t)

        self.reset()

  def inject_summary(self, tag_dict, t):
    summary_str_lists = self.sess.run([self.summary_ops[tag] for tag in tag_dict.keys()], {
      self.summary_placeholders[tag]: value for tag, value in tag_dict.items()
    })
    for summary_str in summary_str_lists:
      self.writer.add_summary(summary_str, t)

  def save_model(self, t):
    logger.info("Saving checkpoints...")
    model_name = type(self).__name__

    if not os.path.exists(self.model_dir):
      os.makedirs(self.model_dir)
    self.saver.save(self.sess, self.model_dir, global_step=t)

  def load_model(self):
    logger.info("Loading checkpoints...")
    tf.initialize_all_variables().run()

    ckpt = tf.train.get_checkpoint_state(self.model_dir)
    if ckpt and ckpt.model_checkpoint_path:
      ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
      fname = os.path.join(self.model_dir, ckpt_name)
      self.saver.restore(self.sess, fname)
      logger.info("Load SUCCESS: %s" % fname)
    else:
      logger.info("Load FAILED: %s" % self.model_dir)

    self.t = self.t_add_op.eval(session=self.sess)
