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
            self._path_gen_generator = dir / "generator_generation.md"
            with self._path_gen_generator.open('r+') as f:
                self._tem_gen_generator = Template(f.read())
                    
            self._path_gen_parser = dir / "parser_generation.md"
            with self._path_gen_parser.open('r+') as f:
                self._tem_gen_parser = Template(f.read())
                
            self._path_res_query = dir / "response_query.md"
            with self._path_res_query.open('r+') as f:
                self._tem_res_query = Template(f.read())
            
            self._path_req_query = dir / "request_query.md"
            with self._path_req_query.open('r+') as f:
                self._tem_req_query = Template(f.read())
                
            self._path_doc_analyze = dir / "doc_analyze.md" 
            with self._path_doc_analyze.open('r+') as f:
                self._tem_doc_analyze = Template(f.read())
            
            self._path_ir_generation = dir / "ir_generation.md"
            with self._path_ir_generation.open('r+') as f:
                self._tem_ir_generation = Template(f.read())
            
            self._path_ir_repair = dir / "ir_repair.md"
            with self._path_ir_repair.open('r+') as f:
                self._tem_ir_repair = Template(f.read())
            
            self._path_initial_symbols = dir / "initial_symbols.md"
            with self._path_initial_symbols.open('r+') as f:
                self._tem_initial_symbols = Template(f.read())
            
            self._path_possible_response = dir / "possible_response.md"
            with self._path_possible_response.open('r+') as f:
                self._tem_possible_response = Template(f.read())
            
            self._path_infer_dependency = dir / "infer_dependency.md"
            with self._path_infer_dependency.open('r+') as f:
                self._tem_infer_dependency = Template(f.read())
            
            self._path_evolve_generator = dir / "generator_evolve.md"
            with self._path_evolve_generator.open('r+') as f:
                self._tem_generator_evolve = Template(f.read())
                
            self._path_try_again = dir / "try_again.md"
            with self._path_try_again.open('r+') as f:
                self._tem_try_again = Template(f.read())
                
            self._path_mutator_evolve = dir / 'mutator_evolve.md'
            with self._path_mutator_evolve.open('r+') as f:
                self._tem_mutator_evolve = Template(f.read())
                
            self._path_mutator_havoc = dir / 'mutator_havoc.md'
            with self._path_mutator_havoc.open('r+') as f:
                self._tem_mutator_havoc = Template(f.read())
                
        except Exception as e:
            logger.error(f'Prompter Init Error: {e}')
            exit(0)
    