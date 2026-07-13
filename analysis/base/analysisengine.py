class AnalysisEngine:

    def __init__(self, skills):
        self.skills = skills

    def analyze(self, company):

        results = {}

        for skill in self.skills:
            results[skill.name] = skill.run(company)

        return results