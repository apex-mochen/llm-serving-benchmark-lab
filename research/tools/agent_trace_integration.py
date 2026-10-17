"""CPU component integration against pinned GuideLLM, with mocked backend/IPC.

No HTTP traffic, token generation, GPU measurements, or real-time sleeps.
"""
import asyncio
import json
import math
import unittest
from multiprocessing import get_context
from unittest.mock import patch

from guidellm.scheduler import TraceReplayStrategy
from guidellm.scheduler.dag import DAGExecutionState
from guidellm.scheduler.schemas import ConversationEdge, ConversationGraph, ConversationNode
from guidellm.scheduler.worker import WorkerProcess
from guidellm.schemas import RequestInfo, RequestSettings


def graph_from_trace(rows):
    """Strict two-turn research adapter; do not silently assume zero duration."""
    if not rows or len({r['session_id'] for r in rows}) != 1:
        raise ValueError('one nonempty session required')
    nodes, infos, edges = {}, {}, []
    for row in rows:
        for key in ['timestamp', 'duration']:
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f'invalid or missing {key}')
        nid = row['request_id']
        if nid in nodes:
            raise ValueError('duplicate request ID')
        settings = RequestSettings(relative_timestamp=row['timestamp'], trace_duration=row['duration'])
        nodes[nid] = ConversationNode(node_id=nid, agent_id=row['tenant_id'], request=row['prompt'], settings=settings)
        parents = row.get('parents', [])
        infos[nid] = RequestInfo(request_id=nid, conversation_id=row['session_id'], node_id=nid,
                                parent_node_ids=parents, settings=settings)
        edges.extend(ConversationEdge(source_node_id=p, target_node_id=nid) for p in parents)
    return ConversationGraph(graph_id=rows[0]['session_id'], nodes=nodes, edges=edges, request_infos=infos)


TRACE = [
    dict(session_id='synthetic-session', tenant_id='tenant-a', request_id='r1', timestamp=0., duration=1., prompt='synthetic first turn'),
    dict(session_id='synthetic-session', tenant_id='tenant-a', request_id='r2', timestamp=3., duration=1., prompt='synthetic second turn', parents=['r1']),
]


class TraceIntegration(unittest.TestCase):
    def setUp(self):
        self.graph = graph_from_trace(TRACE)
        self.state = DAGExecutionState(self.graph)
        self.strategy = TraceReplayStrategy(schedule_turn='idle_gap')
        self.strategy.init_processes_timings(worker_count=1, max_concurrency=1, mp_context=get_context())
        self.strategy.init_processes_start(1000.)

    def test_dependency_and_tool_gap(self):
        with patch('guidellm.scheduler.dag.time.time', return_value=1000.):
            self.state.claim_node('r1')
            with self.assertRaises(ValueError):
                self.state.claim_node('r2')
        parent = self.graph.request_infos['r1']
        parent.timings.request_end = 1010.
        self.strategy.request_completed(parent)
        with patch('guidellm.scheduler.dag.time.time', return_value=1010.):
            self.state.mark_completed('r1', 'request', 'response')
        child = self.graph.request_infos['r2']
        target = asyncio.run(self.strategy.resolve_dequeued_target_start(0, 1000., child.settings, child))
        self.assertEqual(target, 1012.)
        self.assertEqual(self.state.next_node_ready_at()[0], 'r2')

    def test_missing_duration_rejected(self):
        rows = [dict(row) for row in TRACE]
        del rows[0]['duration']
        with self.assertRaises(ValueError):
            graph_from_trace(rows)

    def test_worker_waits_before_dispatch(self):
        worker = WorkerProcess.__new__(WorkerProcess)
        clock, events = [1010.], []
        async def sleep(delay):
            events.append(('sleep', delay))
            clock[0] += delay
        worker._send_update = lambda *args: events.append(('dispatch', clock[0]))
        child = self.graph.request_infos['r2']
        with patch('guidellm.scheduler.worker.time.time', side_effect=lambda: clock[0]), \
             patch('guidellm.scheduler.worker.asyncio.sleep', side_effect=sleep):
            asyncio.run(worker._schedule_request('request', child, 1012.))
        self.assertEqual(events, [('sleep', 2.), ('dispatch', 1012.)])
        self.assertEqual(child.timings.resolve_start, 1012.)

    def test_nonfinite_duration_rejected(self):
        rows = [dict(row) for row in TRACE]
        rows[0]['duration'] = float('nan')
        with self.assertRaises(ValueError):
            graph_from_trace(rows)

    def test_duplicate_id_rejected(self):
        with self.assertRaises(ValueError):
            graph_from_trace([TRACE[0], TRACE[0]])

    def test_cycle_rejected(self):
        rows = [dict(row) for row in TRACE]
        rows[0]['parents'] = ['r2']
        with self.assertRaises(ValueError):
            graph_from_trace(rows)

    def run_worker_case(self, outcome):
        # Real worker completion/error/cancellation methods and real graph state;
        # the backend and IPC are controlled doubles, with a synthetic clock.
        worker = WorkerProcess.__new__(WorkerProcess)
        worker.turns_queue = [self.state]
        worker.strategy = self.strategy
        worker.worker_index = 0
        events = []
        def send(status, response, request, info):
            info.status = status
            events.append((info.node_id, status))
        worker._send_update = send
        async def ready():
            self.state.claim_node('r1')
            return self.state, 'r1'
        worker._get_next_ready_node = ready
        worker._prepare_node = lambda *args: ('request', self.graph.request_infos['r1'])
        async def execute(*args):
            if outcome == 'errored':
                raise RuntimeError('synthetic backend failure')
            if outcome == 'cancelled':
                raise asyncio.CancelledError()
            yield 'synthetic response'
        worker._execute_node = execute
        with patch('guidellm.scheduler.worker.time.time', return_value=1010.):
            if outcome == 'cancelled':
                with self.assertRaises(asyncio.CancelledError):
                    asyncio.run(worker._process_next_graph_node(1000.))
            else:
                asyncio.run(worker._process_next_graph_node(1000.))
        return events

    def test_worker_failure_aborts_child(self):
        self.assertEqual(self.run_worker_case('errored'), [('r1', 'errored'), ('r2', 'cancelled')])
        self.assertTrue(self.state.is_aborted)
        self.assertIsNone(self.state.next_node_ready_at())
        self.assertFalse(self.state.is_complete)

    def test_worker_cancel_aborts_child(self):
        self.assertEqual(self.run_worker_case('cancelled'), [('r1', 'cancelled'), ('r2', 'cancelled')])
        self.assertTrue(self.state.is_aborted)
        self.assertIsNone(self.state.next_node_ready_at())

    def test_worker_success_unlocks_child(self):
        self.assertEqual(self.run_worker_case('completed'), [('r1', 'completed')])
        self.assertFalse(self.state.is_aborted)
        child = self.graph.request_infos['r2']
        target = asyncio.run(self.strategy.resolve_dequeued_target_start(0, 1000., child.settings, child))
        self.assertEqual(target, 1012.)


if __name__ == '__main__':
    unittest.main(verbosity=2)
