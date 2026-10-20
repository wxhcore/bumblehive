from fastmcp import FastMCP

mcp = FastMCP("course-demo")


@mcp.tool()
def get_course_info(course: str) -> str:
    """查询课程的时间和地点。可查询的课程名：Python 入门。"""
    if course == "Python 入门":
        return "周一 10:00，教学楼 A101"
    return "没有找到这门课程"


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
