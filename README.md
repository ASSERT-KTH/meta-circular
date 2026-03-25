# The meta-circular coding agent

See paper [Bootstrapping Coding Agents: The Specification Is the Program}](http://arxiv.org/pdf/2603.17399).
```bibtex
@techreport{2603.17399,
 title = {Bootstrapping Coding Agents: The Specification Is the Program},
 year = {2026},
 author = {Martin Monperrus},
 url = {http://arxiv.org/pdf/2603.17399},
 number = {2603.17399},
 institution = {arXiv},
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

See post [The Coding Agent Bootstrap](https://www.monperrus.net/martin/coding-agent-bootstrap)

Martin Monperrus  
March 2026
