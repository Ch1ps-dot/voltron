import subprocess

class Executor:
    def __init__(self, sut_path, scrip_path:str='') -> None:
        if (scrip_path != ''):
            self.script_path = scrip_path
        self.sut_path = sut_path

    def reset_sut(self):
        try:
            subprocess.run(
                [self.script_path],
                check = True,
                shell = False
            )
        except Exception as e:
            print('Reset Failure')

    def execute_sut(self, args:list = []):
        try:
            subprocess.Popen(
                args = args,
                shell=False
            )
        except Exception as e:
            print('SUT Execution Failure')