"""
Routes for user profile management, academic curriculum, faculty teaching subjects,
and student subject skill curation.
"""

import json
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from app import db
from app.models import Skill, TeacherSubject, User
from app.config import SUBJECTS, SKILL_LEVELS, PROGRAMS
from app.profile.forms import (
    StudentProfileForm,
    TeacherProfileForm,
    ProfileForm,
    SkillForm,
    DeleteSkillForm,
)
from app.auth.routes import validate_student_program_academics

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    View and edit user profile details based on role.
    Students edit curriculum and skills.
    Teachers edit professional information and teaching subjects.
    """
    student_profile_form = StudentProfileForm(prefix="student_profile")
    teacher_profile_form = TeacherProfileForm(prefix="teacher_profile")
    skill_form = SkillForm(prefix="skill")
    delete_form = DeleteSkillForm()

    # Pre-populate forms on initial GET load
    if request.method == "GET":
        if current_user.is_student:
            student_profile_form.name.data = current_user.name
            student_profile_form.email.data = current_user.email
            student_profile_form.college_name.data = current_user.college_name or ""
            student_profile_form.enrollment_no.data = current_user.enrollment_no or ""
            student_profile_form.program.data = current_user.program or "B.Tech"
            student_profile_form.specialization.data = current_user.specialization or current_user.branch or "CSE"
            student_profile_form.year.data = current_user.year or 1
            student_profile_form.semester.data = current_user.semester or 1
            student_profile_form.section.data = current_user.section or ""
            student_profile_form.bio.data = current_user.bio or ""
        else:
            teacher_profile_form.name.data = current_user.name
            teacher_profile_form.email.data = current_user.email
            teacher_profile_form.college_name.data = current_user.college_name or ""
            teacher_profile_form.employee_id.data = current_user.employee_id or ""
            teacher_profile_form.department.data = current_user.department or current_user.branch or "Computer Science"
            teacher_profile_form.designation.data = current_user.designation or "Assistant Professor"
            teacher_profile_form.qualification.data = current_user.qualification or "Ph.D"
            teacher_profile_form.experience_years.data = current_user.experience_years or 1
            teacher_profile_form.subjects.data = current_user.teaching_subject_list
            teacher_profile_form.bio.data = current_user.bio or ""

    # Handle Student Profile Update
    if request.method == "POST" and "student_profile-submit" in request.form:
        if not current_user.is_student:
            abort(403)
        if student_profile_form.validate_on_submit():
            prog = (student_profile_form.program.data or "").strip()
            spec = (student_profile_form.specialization.data or "").strip()
            yr = int(student_profile_form.year.data or 1)
            sem = int(student_profile_form.semester.data or 1)

            is_valid, err = validate_student_program_academics(prog, spec, yr, sem)
            if not is_valid:
                flash(err, "danger")
            else:
                # Check enrollment uniqueness if changed
                clean_enroll = (student_profile_form.enrollment_no.data or "").strip()
                clean_college = (student_profile_form.college_name.data or "").strip()
                existing = User.query.filter(
                    User.id != current_user.id,
                    User.college_name.ilike(clean_college),
                    User.enrollment_no.ilike(clean_enroll),
                ).first()
                if existing:
                    flash("A student with this enrollment number is already registered at this college.", "danger")
                else:
                    current_user.name = (student_profile_form.name.data or "").strip()
                    current_user.college_name = clean_college
                    current_user.enrollment_no = clean_enroll
                    current_user.program = prog
                    current_user.specialization = spec
                    current_user.branch = spec
                    current_user.year = yr
                    current_user.semester = sem
                    current_user.section = (student_profile_form.section.data or "").strip() or None
                    current_user.bio = (student_profile_form.bio.data or "").strip() or None
                    db.session.commit()
                    flash("Academic profile updated successfully!", "success")
                    return redirect(url_for("profile.profile"))

    # Handle Teacher Profile Update
    if request.method == "POST" and "teacher_profile-submit" in request.form:
        if not current_user.is_teacher:
            abort(403)
        if teacher_profile_form.validate_on_submit():
            clean_emp = (teacher_profile_form.employee_id.data or "").strip()
            clean_college = (teacher_profile_form.college_name.data or "").strip()

            existing = User.query.filter(
                User.id != current_user.id,
                User.college_name.ilike(clean_college),
                User.employee_id.ilike(clean_emp),
            ).first()
            if existing:
                flash("A faculty member with this employee ID is already registered at this college.", "danger")
            else:
                current_user.name = (teacher_profile_form.name.data or "").strip()
                current_user.college_name = clean_college
                current_user.employee_id = clean_emp
                current_user.department = (teacher_profile_form.department.data or "").strip()
                current_user.branch = current_user.department
                current_user.designation = (teacher_profile_form.designation.data or "").strip()
                current_user.qualification = (teacher_profile_form.qualification.data or "").strip()
                current_user.experience_years = int(teacher_profile_form.experience_years.data or 0)
                current_user.bio = (teacher_profile_form.bio.data or "").strip() or None

                # Update teaching subjects
                TeacherSubject.query.filter_by(user_id=current_user.id).delete()
                for subj in (teacher_profile_form.subjects.data or []):
                    db.session.add(TeacherSubject(user_id=current_user.id, subject=subj))

                db.session.commit()
                flash("Faculty profile and teaching subjects updated successfully!", "success")
                return redirect(url_for("profile.profile"))

    # Handle Skill Add/Update Submission (Students only)
    if request.method == "POST" and "skill-submit" in request.form:
        if current_user.is_teacher:
            flash("Teacher accounts do not require student skill ratings.", "info")
            return redirect(url_for("profile.profile"))

        if skill_form.validate_on_submit():
            subject = skill_form.subject.data
            level = skill_form.level.data

            if subject not in SUBJECTS or level not in SKILL_LEVELS:
                flash("Invalid subject or skill level submitted.", "danger")
                return redirect(url_for("profile.profile"))

            existing_skill = Skill.query.filter_by(
                user_id=current_user.id, subject=subject
            ).first()

            if existing_skill:
                existing_skill.level = level
                db.session.commit()
                flash(f"Updated skill proficiency for '{subject}' to {level}.", "success")
            else:
                new_skill = Skill(user_id=current_user.id, subject=subject, level=level)
                db.session.add(new_skill)
                db.session.commit()
                flash(f"Added '{subject}' ({level}) to your subject skill profile.", "success")

            return redirect(url_for("profile.profile"))

    # Fetch current user's skills
    user_skills = []
    if current_user.is_student:
        user_skills = (
            Skill.query.filter_by(user_id=current_user.id)
            .order_by(Skill.subject.asc())
            .all()
        )

    # Legacy profile_form object passed for backward-compatibility in template tests
    legacy_profile_form = ProfileForm(prefix="profile")
    legacy_profile_form.name.data = current_user.name
    legacy_profile_form.email.data = current_user.email
    legacy_profile_form.branch.data = current_user.branch or "Computer Science"
    legacy_profile_form.year.data = current_user.year or 1

    return render_template(
        "profile/profile.html",
        title="Profile & Settings",
        user=current_user,
        student_profile_form=student_profile_form,
        teacher_profile_form=teacher_profile_form,
        profile_form=legacy_profile_form,
        skill_form=skill_form,
        delete_form=delete_form,
        user_skills=user_skills,
        programs_json=json.dumps(PROGRAMS),
    )


@profile_bp.route("/profile/skill/delete/<int:skill_id>", methods=["POST"])
@login_required
def delete_skill(skill_id: int):
    """
    Delete a specific skill from the student's profile.
    Enforces CSRF token and ownership checks.
    """
    if current_user.is_teacher:
        flash("Teacher accounts do not maintain skill ratings.", "info")
        return redirect(url_for("profile.profile"))

    skill = Skill.query.get_or_404(skill_id)

    if skill.user_id != current_user.id:
        abort(403)

    subject_name = skill.subject
    db.session.delete(skill)
    db.session.commit()

    flash(f"Removed '{subject_name}' from your subject skill profile.", "info")
    return redirect(url_for("profile.profile"))
