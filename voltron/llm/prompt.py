from string import Template
from pathlib import Path
from voltron.utils.logger import logger

class Prompter:
    """Construct prompt for client
    """
    def __init__(
            self,
            dir: Path
    ) -> None:
        
        # path of prompts
        if not dir.is_dir():
            dir.mkdir()
        
        try:
            self._path_gen_generator = dir / "build" /"generator_generation.md"
            with self._path_gen_generator.open('r+') as f:
                self._tem_gen_generator = Template(f.read())
                    
            self._path_gen_parser = dir / "build" / "parser_generation.md"
            with self._path_gen_parser.open('r+') as f:
                self._tem_gen_parser = Template(f.read())
                
            self._path_res_query = dir / "build" / "response_query.md"
            with self._path_res_query.open('r+') as f:
                self._tem_res_query = Template(f.read())
            
            self._path_req_query = dir / "build" / "request_query.md"
            with self._path_req_query.open('r+') as f:
                self._tem_req_query = Template(f.read())
                
            self._path_doc_analyze = dir / "build" / "doc_analyze.md" 
            with self._path_doc_analyze.open('r+') as f:
                self._tem_doc_analyze = Template(f.read())
            
            self._path_ir_generation = dir / "build" / "ir_generation.md"
            with self._path_ir_generation.open('r+') as f:
                self._tem_ir_generation = Template(f.read())
            
            self._path_ir_repair = dir / "build" / "ir_repair.md"
            with self._path_ir_repair.open('r+') as f:
                self._tem_ir_repair = Template(f.read())
            
            self._path_initial_symbols = dir / "build" / "initial_symbols.md"
            with self._path_initial_symbols.open('r+') as f:
                self._tem_initial_symbols = Template(f.read())
            
            self._path_possible_response = dir / "build" / "possible_response.md"
            with self._path_possible_response.open('r+') as f:
                self._tem_possible_response = Template(f.read())
            
            self._path_infer_dependency = dir / "build" / "infer_dependency.md"
            with self._path_infer_dependency.open('r+') as f:
                self._tem_infer_dependency = Template(f.read())
            
            self._path_evolve_generator = dir / "evolve" / "generator_evolve.md"
            with self._path_evolve_generator.open('r+') as f:
                self._tem_generator_evolve = Template(f.read())
                
            self._path_evolve_parser = dir / "evolve" / "parser_evolve.md"
            with self._path_evolve_parser.open('r+') as f:
                self._tem_parser_evolve = Template(f.read())
                
            self._path_mutator_evolve = dir / "evolve" / 'generator_mutate.md'
            with self._path_mutator_evolve.open('r+') as f:
                self._tem_mutator_evolve = Template(f.read())
                
                
        except Exception as e:
            logger.error(f'Prompter Init Error: {e}')
            exit(0)
    