"""可复现实验：不访问数据库，全部为虚构匹配实例。

运行：PYTHONPATH=backend python scripts/benchmark_optimization.py --output docs/benchmark-results.csv
真实 MySQL 端到端性能由本地环境单独验证；此脚本只比较求解器的 CPU 计算。
"""
from __future__ import annotations
import argparse
import csv
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.services.global_optimization import EdgeCandidate, greedy, optimize


def synthetic_cases(seed=20261014):
    rng=random.Random(seed)
    for count, bed_count, density in [(5,4,0.8),(10,8,0.6),(16,12,0.5),(24,18,0.35),(30,24,0.30)]:
        candidates=[]
        for request_id in range(1,count+1):
            rank=rng.randint(1,5)
            for bed_id in range(100,100+bed_count):
                if rng.random() < density:
                    score=round(30 + 70*rng.random(),2)
                    candidates.append(EdgeCandidate(request_id,bed_id,rank,score))
        yield count,bed_count,candidates


def run(output:Path,seed:int):
    rows=[]
    for people,beds,candidates in synthetic_cases(seed):
        ids=list(range(1,people+1))
        greedy_result=greedy(candidates,ids)
        optimal_result=optimize(candidates,ids,'flow')
        assert optimal_result.proven_optimal
        assert optimal_result.admitted >= greedy_result.admitted
        rows.append({
            'seed': seed, 'patients': people, 'beds': beds, 'edges': len(candidates),
            'greedy_admitted': greedy_result.admitted,
            'exact_admitted': optimal_result.admitted,
            'greedy_priority_sum': greedy_result.priority_sum,
            'exact_priority_sum': optimal_result.priority_sum,
            'greedy_score_sum': greedy_result.score_sum,
            'exact_score_sum': optimal_result.score_sum,
            'greedy_ms': greedy_result.runtime_ms,
            'exact_ms': optimal_result.runtime_ms,
        })
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--seed',type=int,default=20261014)
    parser.add_argument('--output',type=Path,default=ROOT/'docs'/'p1_benchmark_synthetic.csv')
    args=parser.parse_args()
    for row in run(args.output,args.seed):
        print(f"模拟批次 {row['patients']} 人/{row['beds']} 床, 贪心={row['greedy_admitted']}, 全局={row['exact_admitted']}, 全局耗时={row['exact_ms']} ms")
