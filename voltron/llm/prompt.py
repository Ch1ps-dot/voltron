from string import Template
from pathlib import Path
from voltron.utils.logger import logger_fuzz as logger

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

            self._path_code_repair = dir / "builder" / "code_repair.md"
            with self._path_code_repair.open('r+') as f:
                self._tem_code_repair = Template(f.read())

            self._path_gen_checker = dir / "builder" / "checker_generation.md"
            with self._path_gen_checker.open('r+') as f:
                self._tem_gen_checker = Template(f.read())

            self._path_gen_observer = dir / "builder" / "observer_generation.md"
            with self._path_gen_observer.open('r+') as f:
                self._tem_gen_observer = Template(f.read())
                
            self._path_res_query = dir / "builder" / "response_query.md"
            with self._path_res_query.open('r+') as f:
                self._tem_res_query = Template(f.read())
            
            self._path_req_query = dir / "builder" / "request_query.md"
            with self._path_req_query.open('r+') as f:
                self._tem_req_query = Template(f.read())

            self._path_req_type_rules = dir / "builder" / "request_type_rules.md"
            with self._path_req_type_rules.open('r+') as f:
                self._tem_req_type_rules = Template(f.read())

            self._path_res_type_rules = dir / "builder" / "response_type_rules.md"
            with self._path_res_type_rules.open('r+') as f:
                self._tem_res_type_rules = Template(f.read())

            self._path_section_type_annotation = (
                dir / "builder" / "section_type_annotation.md"
            )
            with self._path_section_type_annotation.open('r+') as f:
                self._tem_section_type_annotation = Template(f.read())
                
            self._path_doc_analyze = dir / "builder" / "doc_analyze.md" 
            with self._path_doc_analyze.open('r+') as f:
                self._tem_doc_analyze = Template(f.read())
            
            self._path_ir_generation = dir / "builder" / "ir_generation.md"
            with self._path_ir_generation.open('r+') as f:
                self._tem_ir_generation = Template(f.read())
            
            self._path_ir_repair = dir / "builder" / "ir_repair.md"
            with self._path_ir_repair.open('r+') as f:
                self._tem_ir_repair = Template(f.read())

            self._path_ir_evolve = dir / "evolver" / "ir_evolve.md"
            with self._path_ir_evolve.open('r+') as f:
                self._tem_ir_evolve = Template(f.read())
            
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

            self._path_checker_evolve = dir / "evolver" / "checker_evolve.md"
            with self._path_checker_evolve.open('r+') as f:
                self._tem_checker_evolve = Template(f.read())

            self._path_observer_evolve = dir / "evolver" / "observer_evolve.md"
            with self._path_observer_evolve.open('r+') as f:
                self._tem_observer_evolve = Template(f.read())

            self._path_observer_semantic_compare = (
                dir / "evolver" / "observer_semantic_compare.md"
            )
            with self._path_observer_semantic_compare.open('r+') as f:
                self._tem_observer_semantic_compare = Template(f.read())

        except Exception:
            logger.exception('Prompter initialization failed')
            exit(0)
