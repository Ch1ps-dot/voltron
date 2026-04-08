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
            self._path_gen_generator = dir / "builder" /"generator_generation.md"
            with self._path_gen_generator.open('r+') as f:
                self._tem_gen_generator = Template(f.read())
                    
            self._path_gen_parser = dir / "builder" / "parser_generation.md"
            with self._path_gen_parser.open('r+') as f:
                self._tem_gen_parser = Template(f.read())
                
            self._path_res_query = dir / "builder" / "response_query.md"
            with self._path_res_query.open('r+') as f:
                self._tem_res_query = Template(f.read())
            
            self._path_req_query = dir / "builder" / "request_query.md"
            with self._path_req_query.open('r+') as f:
                self._tem_req_query = Template(f.read())
                
            self._path_doc_analyze = dir / "builder" / "doc_analyze.md" 
            with self._path_doc_analyze.open('r+') as f:
                self._tem_doc_analyze = Template(f.read())
            
            self._path_ir_generation = dir / "builder" / "ir_generation.md"
            with self._path_ir_generation.open('r+') as f:
                self._tem_ir_generation = Template(f.read())
            
            self._path_ir_repair = dir / "builder" / "ir_repair.md"
            with self._path_ir_repair.open('r+') as f:
                self._tem_ir_repair = Template(f.read())
            
            self._path_initial_symbols = dir / "builder" / "initial_symbols.md"
            with self._path_initial_symbols.open('r+') as f:
                self._tem_initial_symbols = Template(f.read())
            
            self._path_possible_response = dir / "builder" / "possible_response.md"
            with self._path_possible_response.open('r+') as f:
                self._tem_possible_response = Template(f.read())
            
            self._path_infer_dependency = dir / "builder" / "infer_dependency.md"
            with self._path_infer_dependency.open('r+') as f:
                self._tem_infer_dependency = Template(f.read())
            
            self._path_evolve_generator = dir / "evolver" / "generator_evolve.md"
            with self._path_evolve_generator.open('r+') as f:
                self._tem_generator_evolve = Template(f.read())
                
            self._path_evolve_parser = dir / "evolver" / "parser_evolve.md"
            with self._path_evolve_parser.open('r+') as f:
                self._tem_parser_evolve = Template(f.read())
                
            self._path_mutator_evolve = dir / "evolver" / 'generator_mutate.md'
            with self._path_mutator_evolve.open('r+') as f:
                self._tem_mutator_evolve = Template(f.read())
                
                
        except Exception as e:
            logger.error(f'Prompter Init Error: {e}')
            exit(0)
    