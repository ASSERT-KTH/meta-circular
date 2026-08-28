# The meta-circular bootstrapped coding agent

See  [Bootstrapping Coding Agents: The Specification Is the Program](http://oadoi.org/10.1109/ms.2026.3687051), In IEEE Software, volume 43, 2026.

Martin Monperrus  
March 2026

## Concept

See paper [Bootstrapping Coding Agents: The Specification Is the Program}](http://arxiv.org/pdf/2603.17399).
```bibtex
@article{bootstrapping-agent,
 title = {Bootstrapping Coding Agents: The Specification Is the Program},
 year = {2026},
 author = {Martin Monperrus},
 url = {http://arxiv.org/pdf/2603.17399},
 journal = {IEEE Software},
 volume = {43},
 issue = {4},
 doi = {10.1109/ms.2026.3687051},
}
```

**Step 1: specification.** We write a specification for a coding agent. The resulting [spec](https://github.com/ASSERT-KTH/meta-circular/blob/main/spec.md)t defines the agent's interface, its expected behavior, and the constraints it must respect.

**Step 2: first implementation.** Claude Code implements the spec (model Sonnet 4.6). The result is a perfectly working Python program ([agent.py](https://github.com/ASSERT-KTH/meta-circular/blob/main/agent.py)).

> implement the spec in a single python file

```
$ python agent.py 
usage: agent.py [-h] [--model MODEL] [--base-url BASE_URL] [--api-key API_KEY] [--max-turns MAX_TURNS] [--cwd CWD] [task]
```

**Step 3: self-implementation.** The newly generated agent is given the same specification and asked to implement it again. It succeeds. The agent reimplements itself. Meta-circularity ✓.

```
$ python agent.py "implement the spec in a single python file"
```

## Changelog

The spec could actually be made simpler, see [spec-simpler](https://github.com/ASSERT-KTH/meta-circular/blob/main/spec-simpler.md) with tools `list_files` and `search_text` removed.